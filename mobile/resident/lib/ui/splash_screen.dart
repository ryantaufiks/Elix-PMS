import 'package:flutter/material.dart';

import '../theme.dart';

/// ELIX logo on navy with a breathing blue glow, shown while the app starts.
class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});
  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> with SingleTickerProviderStateMixin {
  late final _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 1800))..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final still = MediaQuery.of(context).disableAnimations;
    return Scaffold(
      backgroundColor: navyDeep,
      body: Center(
        child: TweenAnimationBuilder<double>(
          // The logo fades and settles in once, then the glow behind it breathes.
          tween: Tween(begin: still ? 1 : 0, end: 1),
          duration: const Duration(milliseconds: 700),
          curve: Curves.easeOutCubic,
          builder: (context, appear, child) => Opacity(opacity: appear, child: Transform.scale(scale: 0.9 + 0.1 * appear, child: child)),
          child: AnimatedBuilder(
            animation: _controller,
            builder: (context, child) {
              final t = still ? 0.5 : Curves.easeInOut.transform(_controller.value);
              return Container(
                width: 280,
                height: 280,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(colors: [
                    brandBlue.withValues(alpha: 0.30 + 0.25 * t),
                    const Color(0xFF00B4FF).withValues(alpha: 0.10 * t),
                    brandBlue.withValues(alpha: 0),
                  ], stops: const [0, 0.45, 1]),
                ),
                child: child,
              );
            },
            child: Image.asset('assets/elix-logo.png', height: 64, semanticLabel: 'Elix'),
          ),
        ),
      ),
    );
  }
}
