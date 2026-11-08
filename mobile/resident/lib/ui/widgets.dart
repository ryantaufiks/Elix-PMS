import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../api.dart';

final _dateTime = DateFormat('EEE d MMM, HH:mm');
final _time = DateFormat('HH:mm');
String formatDateTime(DateTime t) => _dateTime.format(t);

String timeAgo(DateTime t) {
  final d = DateTime.now().difference(t);
  if (d.inMinutes < 1) return 'just now';
  if (d.inHours < 1) return '${d.inMinutes} min ago';
  if (d.inDays < 1 && t.day == DateTime.now().day) return _time.format(t);
  return _dateTime.format(t);
}

void showError(BuildContext context, Object error) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$error'), behavior: SnackBarBehavior.floating));
}

void showMessage(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message), behavior: SnackBarBehavior.floating));
}

/// "Supported by … / © 2026" line shown at the foot of the login and profile screens.
class Credit extends StatelessWidget {
  const Credit({super.key, this.color});
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final style = TextStyle(color: color ?? Theme.of(context).colorScheme.outline, fontSize: 12, height: 1.5);
    return Text('Supported by Smart City Technologies Pte Ltd\n© 2026 Elix PMS. All rights reserved.', textAlign: TextAlign.center, style: style);
  }
}

/// Image from an endpoint that needs the JWT (QR codes, visitor snapshots).
class AuthImage extends StatefulWidget {
  const AuthImage(this.path, {super.key, this.fit = BoxFit.cover});
  final String path;
  final BoxFit fit;
  @override
  State<AuthImage> createState() => _AuthImageState();
}

class _AuthImageState extends State<AuthImage> {
  late Future<Uint8List> _bytes = Api.instance.bytes(widget.path);
  @override
  void didUpdateWidget(AuthImage old) {
    super.didUpdateWidget(old);
    if (old.path != widget.path) _bytes = Api.instance.bytes(widget.path);
  }

  @override
  Widget build(BuildContext context) => FutureBuilder(
        future: _bytes,
        builder: (context, snap) {
          if (snap.hasData) return Image.memory(snap.data!, fit: widget.fit, gaplessPlayback: true);
          if (snap.hasError) return const Center(child: Icon(Icons.image_not_supported_outlined));
          return const Center(child: CircularProgressIndicator(strokeWidth: 2));
        },
      );
}

class StatusChip extends StatelessWidget {
  const StatusChip(this.label, {super.key, required this.color});
  final String label;
  final Color color;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(6)),
        child: Text(label, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600)),
      );
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.icon, required this.text});
  final IconData icon;
  final String text;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 48, horizontal: 24),
        child: Column(children: [
          Icon(icon, size: 40, color: Theme.of(context).colorScheme.outline),
          const SizedBox(height: 12),
          Text(text, textAlign: TextAlign.center, style: TextStyle(color: Theme.of(context).colorScheme.outline)),
        ]),
      );
}

/// Drag the knob to the end to confirm (the gate really opens). Also usable with accessibility tap.
class SwipeToUnlock extends StatefulWidget {
  const SwipeToUnlock({super.key, required this.onUnlock, this.label = 'Swipe to open gate'});
  final Future<void> Function() onUnlock;
  final String label;
  @override
  State<SwipeToUnlock> createState() => _SwipeToUnlockState();
}

class _SwipeToUnlockState extends State<SwipeToUnlock> {
  double _offset = 0;
  bool _busy = false;
  static const _knob = 60.0;

  Future<void> _fire(double max) async {
    setState(() {
      _busy = true;
      _offset = max;
    });
    try {
      await widget.onUnlock();
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _offset = 0;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(builder: (context, constraints) {
        final max = constraints.maxWidth - _knob - 8;
        return Semantics(
          button: true,
          label: widget.label,
          onTap: _busy ? null : () => _fire(max),
          child: Container(
            height: _knob + 8,
            decoration: BoxDecoration(color: const Color(0xFF16A34A), borderRadius: BorderRadius.circular(40)),
            child: Stack(alignment: Alignment.centerLeft, children: [
              Center(
                child: Padding(
                  padding: const EdgeInsets.only(left: 48),
                  child: Text(_busy ? 'Opening…' : widget.label,
                      style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600)),
                ),
              ),
              AnimatedPositioned(
                duration: Duration(milliseconds: _dragging ? 0 : 200),
                left: 4 + _offset,
                child: GestureDetector(
                  onHorizontalDragStart: _busy ? null : (_) => setState(() => _dragging = true),
                  onHorizontalDragUpdate: _busy ? null : (d) => setState(() => _offset = (_offset + d.delta.dx).clamp(0, max)),
                  onHorizontalDragEnd: _busy
                      ? null
                      : (_) {
                          setState(() => _dragging = false);
                          if (_offset >= max * 0.9) {
                            _fire(max);
                          } else {
                            setState(() => _offset = 0);
                          }
                        },
                  child: Container(
                    width: _knob,
                    height: _knob,
                    decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
                    child: _busy
                        ? const Padding(padding: EdgeInsets.all(18), child: CircularProgressIndicator(strokeWidth: 2.5))
                        : const Icon(Icons.lock_open_rounded, color: Color(0xFF16A34A), size: 28),
                  ),
                ),
              ),
            ]),
          ),
        );
      });

  bool _dragging = false;
}
