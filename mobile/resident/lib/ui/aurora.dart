import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme.dart';

/// Navy background with soft blue glows drifting slowly behind the content (login screen).
class AuroraBackground extends StatefulWidget {
  const AuroraBackground({super.key, required this.child});
  final Widget child;

  @override
  State<AuroraBackground> createState() => _AuroraBackgroundState();
}

class _AuroraBackgroundState extends State<AuroraBackground> with SingleTickerProviderStateMixin {
  late final _controller = AnimationController(vsync: this, duration: const Duration(seconds: 16))..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Respect "Remove animations" in the phone's accessibility settings.
    final still = MediaQuery.of(context).disableAnimations;
    return Stack(fit: StackFit.expand, children: [
      RepaintBoundary(
        child: still
            ? CustomPaint(painter: _AuroraPainter(0))
            : AnimatedBuilder(animation: _controller, builder: (_, _) => CustomPaint(painter: _AuroraPainter(_controller.value))),
      ),
      widget.child,
    ]);
  }
}

class _Glow {
  const _Glow(this.color, this.radius, this.x, this.y, this.dx, this.dy, this.speed, this.phase);
  final Color color;
  final double radius; // Share of the screen's longer side.
  final double x, y; // Centre of its orbit, 0..1.
  final double dx, dy; // How far it drifts.
  final int speed; // Whole turns per cycle, so the loop is seamless.
  final double phase;
}

const _glows = [
  _Glow(Color(0xFF2F6FFF), 0.55, 0.25, 0.20, 0.32, 0.18, 1, 0),
  _Glow(Color(0xFF2448C8), 0.60, 0.80, 0.40, 0.28, 0.26, 1, 2.1),
  _Glow(Color(0xFF00B4FF), 0.42, 0.50, 0.75, 0.38, 0.16, 2, 4.2),
  _Glow(Color(0xFF6D4BFF), 0.38, 0.15, 0.85, 0.24, 0.20, 1, 1.3),
];

class _AuroraPainter extends CustomPainter {
  _AuroraPainter(this.t);
  final double t;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = navyDeep);
    final longest = math.max(size.width, size.height);
    for (final g in _glows) {
      final a = 2 * math.pi * t * g.speed + g.phase;
      final centre = Offset((g.x + g.dx * math.sin(a)) * size.width, (g.y + g.dy * math.cos(a * 0.8 + 1)) * size.height);
      final radius = g.radius * longest * (1 + 0.18 * math.sin(a * 1.3));
      canvas.drawCircle(
        centre,
        radius,
        Paint()
          ..shader = RadialGradient(colors: [g.color.withValues(alpha: 0.6), g.color.withValues(alpha: 0)])
              .createShader(Rect.fromCircle(center: centre, radius: radius)),
      );
    }
  }

  @override
  bool shouldRepaint(_AuroraPainter old) => old.t != t;
}
