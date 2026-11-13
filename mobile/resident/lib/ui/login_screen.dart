import 'dart:ui';

import 'package:flutter/material.dart';

import '../session.dart';
import '../theme.dart';
import 'aurora.dart';
import 'web_page_screen.dart';
import 'widgets.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _username = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  bool _hide = true;
  String? _error;

  Future<void> _submit() async {
    if (_username.text.trim().isEmpty || _password.text.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await Session.instance.login(_username.text.trim().toLowerCase(), _password.text);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: navyDeep,
      body: AuroraBackground(
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  Image.asset('assets/elix-logo.png', height: 56, semanticLabel: 'Elix'),
                  const SizedBox(height: 12),
                  const Text('Engage Link Identified Experience', textAlign: TextAlign.center,
                      style: TextStyle(color: Color(0xFFCBD5E1), fontSize: 13, letterSpacing: 1.6)),
                  const SizedBox(height: 40),
                  _Glass(
                    child: AutofillGroup(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                        const Text('Sign in', style: TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.w600)),
                        const SizedBox(height: 4),
                        const Text('Use the login from your condo management.', style: TextStyle(color: Color(0xFFB4C2DA))),
                        const SizedBox(height: 20),
                        if (_error != null) ...[
                          Text(_error!, style: const TextStyle(color: Color(0xFFFCA5A5))),
                          const SizedBox(height: 12),
                        ],
                        TextField(
                          controller: _username,
                          autofillHints: const [AutofillHints.username],
                          textInputAction: TextInputAction.next,
                          style: const TextStyle(color: Colors.white),
                          cursorColor: Colors.white,
                          decoration: _glassField('Username', Icons.person_outline_rounded),
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          controller: _password,
                          obscureText: _hide,
                          autofillHints: const [AutofillHints.password],
                          onSubmitted: (_) => _submit(),
                          style: const TextStyle(color: Colors.white),
                          cursorColor: Colors.white,
                          decoration: _glassField('Password', Icons.lock_outline_rounded).copyWith(
                            suffixIcon: IconButton(
                              color: const Color(0xFFB4C2DA),
                              icon: Icon(_hide ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                              onPressed: () => setState(() => _hide = !_hide),
                            ),
                          ),
                        ),
                        const SizedBox(height: 24),
                        _GlowButton(busy: _busy, onPressed: _submit),
                      ]),
                    ),
                  ),
                  const SizedBox(height: 24),
                  Center(
                    child: TextButton(
                      onPressed: () => WebPageScreen.open(context, 'Privacy policy', '/privacy/'),
                      child: const Text('Privacy policy', style: TextStyle(color: Color(0xFF94A3B8))),
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Credit(color: Color(0xFF94A3B8)),
                ]),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Frosted panel: blurs the drifting glows behind it, with a faint light edge.
class _Glass extends StatelessWidget {
  const _Glass({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(24);
    return ClipRRect(
      borderRadius: radius,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
        child: Container(
          padding: const EdgeInsets.all(22),
          decoration: BoxDecoration(
            borderRadius: radius,
            border: Border.all(color: Colors.white.withValues(alpha: 0.18)),
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [Colors.white.withValues(alpha: 0.14), Colors.white.withValues(alpha: 0.04)],
            ),
          ),
          child: child,
        ),
      ),
    );
  }
}

InputDecoration _glassField(String label, IconData icon) {
  OutlineInputBorder edge(Color color, [double width = 1]) =>
      OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: color, width: width));
  return InputDecoration(
    labelText: label,
    labelStyle: const TextStyle(color: Color(0xFFB4C2DA)),
    floatingLabelStyle: const TextStyle(color: Colors.white),
    prefixIcon: Icon(icon, color: const Color(0xFFB4C2DA)),
    filled: true,
    fillColor: Colors.white.withValues(alpha: 0.08),
    enabledBorder: edge(Colors.white.withValues(alpha: 0.16)),
    focusedBorder: edge(const Color(0xFF7DD3FC), 1.4),
    border: edge(Colors.white.withValues(alpha: 0.16)),
  );
}

/// Sign-in button in the glow's colours (blue to cyan) with a soft halo.
class _GlowButton extends StatelessWidget {
  const _GlowButton({required this.busy, required this.onPressed});
  final bool busy;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(14);
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: radius,
        gradient: const LinearGradient(colors: [Color(0xFF2F6FFF), Color(0xFF00B4FF)]),
        boxShadow: [BoxShadow(color: const Color(0xFF2F8CFF).withValues(alpha: 0.45), blurRadius: 24, offset: const Offset(0, 8))],
      ),
      child: Material(
        type: MaterialType.transparency,
        child: InkWell(
          borderRadius: radius,
          onTap: busy ? null : onPressed,
          child: SizedBox(
            height: 52,
            child: Center(
              child: busy
                  ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                  : const Text('Sign in', style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600, letterSpacing: 0.4)),
            ),
          ),
        ),
      ),
    );
  }
}
