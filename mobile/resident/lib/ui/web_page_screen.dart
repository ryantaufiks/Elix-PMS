import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../config.dart';

/// Public pages of the web app (privacy policy, account deletion) shown inside the app.
class WebPageScreen extends StatefulWidget {
  const WebPageScreen({super.key, required this.title, required this.path});
  final String title;
  final String path;

  static void open(BuildContext context, String title, String path) =>
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => WebPageScreen(title: title, path: path)));

  @override
  State<WebPageScreen> createState() => _WebPageScreenState();
}

class _WebPageScreenState extends State<WebPageScreen> {
  late final WebViewController _web;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _web = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(onPageFinished: (_) {
        if (mounted) setState(() => _loading = false);
      }))
      ..loadRequest(Uri.parse('$apiBase${widget.path}'));
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(widget.title)),
        body: Stack(children: [
          WebViewWidget(controller: _web),
          if (_loading) const Center(child: CircularProgressIndicator()),
        ]),
      );
}
