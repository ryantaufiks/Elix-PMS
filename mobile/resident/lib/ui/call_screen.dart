import 'dart:async';

import 'package:flutter/material.dart';
import 'package:livekit_client/livekit_client.dart';
import 'package:permission_handler/permission_handler.dart';

import '../api.dart';
import '../calls.dart';
import '../models.dart';
import '../theme.dart';
import 'widgets.dart';

/// Answered call: the kiosk's live video, two-way audio, optional own camera, and swipe to open.
class CallScreen extends StatefulWidget {
  const CallScreen({super.key, required this.callId});
  final int callId;
  @override
  State<CallScreen> createState() => _CallScreenState();
}

class _CallScreenState extends State<CallScreen> with WidgetsBindingObserver {
  Room? _room;
  EventsListener<RoomEvent>? _listener;
  VideoTrack? _remoteVideo;
  IntercomCall? _call;
  String _state = 'Connecting…';
  bool _mic = true;
  bool _camera = false;
  bool _closing = false;
  StreamSubscription? _updates;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _start();
    _updates = Calls.instance.updates.listen((call) {
      if (call.id != widget.callId) return;
      setState(() => _call = call);
      if (!call.isOpen) _close(message: call.status == 'approved' ? null : 'Call ended.');
    });
  }

  Future<void> _start() async {
    await [Permission.microphone, Permission.camera].request();
    try {
      final data = await Api.instance.post('/v1/intercom-calls/${widget.callId}/answer/') as Map<String, dynamic>;
      _call = IntercomCall((data['call'] as Map).cast<String, dynamic>());
      final lk = (data['livekit'] as Map).cast<String, dynamic>();
      final room = Room(roomOptions: const RoomOptions(adaptiveStream: true, dynacast: true));
      _room = room;
      _listener = room.createListener()
        ..on<TrackSubscribedEvent>((_) => _refreshTracks())
        ..on<TrackUnsubscribedEvent>((_) => _refreshTracks())
        ..on<RoomDisconnectedEvent>((_) => _close(message: 'Call ended.'));
      await room.connect(lk['url'] as String, lk['token'] as String);
      await room.localParticipant?.setMicrophoneEnabled(true);
      _refreshTracks();
      if (mounted) setState(() => _state = 'Connected');
    } on ApiException catch (e) {
      _close(message: e.status == 409 ? e.message : 'Could not answer: ${e.message}');
    } catch (e) {
      if (mounted) setState(() => _state = 'Video unavailable. You can still open the gate.');
    }
  }

  void _refreshTracks() {
    VideoTrack? video;
    for (final p in _room?.remoteParticipants.values ?? const <RemoteParticipant>[]) {
      for (final pub in p.videoTrackPublications) {
        if (pub.subscribed && pub.track != null) video = pub.track as VideoTrack;
      }
    }
    if (mounted) setState(() => _remoteVideo = video);
  }

  Future<void> _unlock() async {
    try {
      await Api.instance.post('/v1/intercom-calls/${widget.callId}/unlock/');
      if (mounted) showMessage(context, 'Gate opening for your visitor.');
      await _close();
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  Future<void> _hangUp() async {
    try {
      await Api.instance.post('/v1/intercom-calls/${widget.callId}/hangup/');
    } catch (_) {}
    await _close();
  }

  Future<void> _close({String? message}) async {
    if (_closing) return;
    _closing = true;
    Calls.instance.finished(widget.callId);
    await _listener?.dispose();
    await _room?.disconnect();
    await _room?.dispose();
    if (!mounted) return;
    if (message != null) showMessage(context, message);
    Navigator.of(context).maybePop();
  }

  /// The app is being closed mid-call: end the call so the kiosk does not keep waiting.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.detached && !_closing) _hangUp();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _updates?.cancel();
    if (!_closing) {
      Calls.instance.finished(widget.callId);
      _listener?.dispose();
      _room?.disconnect();
      _room?.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final local = _room?.localParticipant?.videoTrackPublications.firstOrNull?.track as VideoTrack?;
    return PopScope(
      canPop: _closing,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _hangUp();
      },
      child: Scaffold(
        backgroundColor: navyDeep,
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(children: [
              Text(_call == null || _call!.visitorName.isEmpty ? (_call?.kioskName ?? 'Visitor') : _call!.visitorName,
                  style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w600)),
              Text(
                  _call == null
                      ? _state
                      : [if (_call!.purposeLine.isNotEmpty) _call!.purposeLine, _call!.kioskName, _state].join(' · '),
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white60)),
              const SizedBox(height: 16),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(24),
                  child: Stack(fit: StackFit.expand, children: [
                    Container(color: const Color(0xFF13203A)),
                    if (_remoteVideo != null)
                      VideoTrackRenderer(_remoteVideo!, fit: VideoViewFit.cover)
                    else
                      const Center(child: Icon(Icons.videocam_off_outlined, size: 72, color: Colors.white24)),
                    if (_camera && local != null)
                      Positioned(
                        right: 12,
                        top: 12,
                        width: 96,
                        height: 128,
                        child: ClipRRect(borderRadius: BorderRadius.circular(12), child: VideoTrackRenderer(local, fit: VideoViewFit.cover, mirrorMode: VideoViewMirrorMode.mirror)),
                      ),
                  ]),
                ),
              ),
              const SizedBox(height: 20),
              SwipeToUnlock(onUnlock: _unlock),
              const SizedBox(height: 16),
              Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
                IconButton.filledTonal(
                  iconSize: 28,
                  onPressed: _room == null ? null : () async {
                    await _room!.localParticipant?.setMicrophoneEnabled(!_mic);
                    setState(() => _mic = !_mic);
                  },
                  icon: Icon(_mic ? Icons.mic : Icons.mic_off),
                  tooltip: _mic ? 'Mute' : 'Unmute',
                ),
                IconButton.filled(
                  iconSize: 32,
                  style: IconButton.styleFrom(backgroundColor: const Color(0xFFDC2626), padding: const EdgeInsets.all(18)),
                  onPressed: _hangUp,
                  icon: const Icon(Icons.call_end, color: Colors.white),
                  tooltip: 'Hang up',
                ),
                IconButton.filledTonal(
                  iconSize: 28,
                  onPressed: _room == null ? null : () async {
                    await _room!.localParticipant?.setCameraEnabled(!_camera);
                    setState(() => _camera = !_camera);
                  },
                  icon: Icon(_camera ? Icons.videocam : Icons.videocam_off),
                  tooltip: _camera ? 'Stop my camera' : 'Show my camera',
                ),
              ]),
            ]),
          ),
        ),
      ),
    );
  }
}
