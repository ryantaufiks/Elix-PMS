import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'appearance.dart';
import 'calls.dart';
import 'push.dart';
import 'realtime.dart';
import 'session.dart';
import 'theme.dart';
import 'ui/home_shell.dart';
import 'ui/login_screen.dart';
import 'ui/splash_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Draw the UI first: nothing below may keep the screen blank (slow network, waking from lock screen).
  runApp(const ElixApp());
  await Appearance.instance.restore();
  await Session.instance.restore();
  await Push.instance.init();
  if (Session.instance.me != null) Push.instance.register();
  Calls.instance.start();
}

class ElixApp extends StatefulWidget {
  const ElixApp({super.key});
  @override
  State<ElixApp> createState() => _ElixAppState();
}

class _ElixAppState extends State<ElixApp> with WidgetsBindingObserver {
  // The splash stays up at least this long, so it reads as a splash rather than a flicker.
  bool _splashShown = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    Future.delayed(const Duration(milliseconds: 1600), () {
      if (mounted) setState(() => _splashShown = true);
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      Realtime.instance.kick();
      Calls.instance.reconcile();
    }
  }

  @override
  Widget build(BuildContext context) {
    SystemChrome.setSystemUIOverlayStyle(SystemUiOverlayStyle.dark.copyWith(statusBarColor: Colors.transparent));
    return ListenableBuilder(
      listenable: Appearance.instance,
      builder: (context, _) => MaterialApp(
        title: 'Elix',
        debugShowCheckedModeBanner: false,
        navigatorKey: navigatorKey,
        theme: buildTheme(Brightness.light),
        darkTheme: buildTheme(Brightness.dark),
        themeMode: Appearance.instance.mode,
        home: ListenableBuilder(
          listenable: Session.instance,
          builder: (context, _) {
            final session = Session.instance;
            final Widget screen = session.loading || !_splashShown
                ? const SplashScreen()
                : session.me == null
                    ? const LoginScreen()
                    : const HomeShell();
            return AnimatedSwitcher(duration: const Duration(milliseconds: 500), child: screen);
          },
        ),
      ),
    );
  }
}
