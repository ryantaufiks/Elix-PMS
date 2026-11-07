import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../calls.dart';
import '../models.dart';
import '../theme.dart';
import 'widgets.dart';

/// Shown while a kiosk is ringing this unit and the app is open: see who is there, then answer,
/// decline, or open the gate straight away (e.g. a courier).
class IncomingCallScreen extends StatefulWidget {
  const IncomingCallScreen({super.key, required this.call});
  final IntercomCall call;
  @override
  State<IncomingCallScreen> createState() => _IncomingCallScreenState();
}

class _IncomingCallScreenState extends State<IncomingCallScreen> {
  StreamSubscription? _sub;

  @override
  void initState() {
    super.initState();
    _sub = Calls.instance.updates.listen((call) {
      if (call.id == widget.call.id && (!call.isOpen || call.status != 'ringing') && mounted) {
        Navigator.of(context).maybePop();
        if (call.status == 'answered') showMessage(context, 'Answered on another phone.');
      }
    });
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  Future<void> _decline() async {
    try {
      await Api.instance.post('/v1/intercom-calls/${widget.call.id}/reject/');
    } catch (_) {}
    if (mounted) Navigator.of(context).pop();
  }

  Future<void> _unlock() async {
    try {
      await Api.instance.post('/v1/intercom-calls/${widget.call.id}/unlock/');
      if (mounted) {
        Navigator.of(context).pop();
        showMessage(context, 'Gate opening for your visitor.');
      }
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  void _answer() {
    Navigator.of(context).pop();
    Calls.instance.answer(widget.call.id);
  }

  @override
  Widget build(BuildContext context) {
    final call = widget.call;
    return Scaffold(
      backgroundColor: navyDeep,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(children: [
            const SizedBox(height: 12),
            const Text('Visitor at the gate', style: TextStyle(color: Color(0xFF94A3B8), letterSpacing: 1)),
            const SizedBox(height: 6),
            Text(call.kioskName, style: const TextStyle(color: Colors.white, fontSize: 26, fontWeight: FontWeight.w600)),
            Text(call.visitorName.isEmpty ? call.unitDisplay : '${call.visitorName} · ${call.unitDisplay}',
                style: const TextStyle(color: Colors.white70, fontSize: 16)),
            const SizedBox(height: 24),
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(24),
                child: Container(
                  color: const Color(0xFF13203A),
                  width: double.infinity,
                  child: call.hasSnapshot
                      ? AuthImage('/v1/intercom-calls/${call.id}/snapshot/')
                      : const Center(child: Icon(Icons.person_outline, size: 96, color: Colors.white24)),
                ),
              ),
            ),
            const SizedBox(height: 24),
            SwipeToUnlock(onUnlock: _unlock),
            const SizedBox(height: 20),
            Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
              _RoundButton(icon: Icons.call_end, color: const Color(0xFFDC2626), label: 'Decline', onTap: _decline),
              _RoundButton(icon: Icons.videocam, color: brandBlue, label: 'Answer', onTap: _answer),
            ]),
          ]),
        ),
      ),
    );
  }
}

class _RoundButton extends StatelessWidget {
  const _RoundButton({required this.icon, required this.color, required this.label, required this.onTap});
  final IconData icon;
  final Color color;
  final String label;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => Column(children: [
        Material(
          color: color,
          shape: const CircleBorder(),
          child: InkWell(customBorder: const CircleBorder(), onTap: onTap, child: Padding(padding: const EdgeInsets.all(20), child: Icon(icon, color: Colors.white, size: 32))),
        ),
        const SizedBox(height: 8),
        Text(label, style: const TextStyle(color: Colors.white70)),
      ]);
}
