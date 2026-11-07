import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'calls.dart';
import 'push.dart';
import 'realtime.dart';
import 'session.dart';
import 'theme.dart';
import 'ui/home_shell.dart';
import 'ui/login_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Draw the UI first: nothing below may keep the screen blank (slow network, waking from lock screen).
  runApp(const ElixApp());
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
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
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
    return MaterialApp(
      title: 'Elix',
      debugShowCheckedModeBanner: false,
      navigatorKey: navigatorKey,
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      home: ListenableBuilder(
        listenable: Session.instance,
        builder: (context, _) {
          final session = Session.instance;
          if (session.loading) return const Scaffold(body: Center(child: CircularProgressIndicator()));
          return session.me == null ? const LoginScreen() : const HomeShell();
        },
      ),
    );
  }
}
