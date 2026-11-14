import 'dart:async';

import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../api.dart';
import '../realtime.dart';

/// Opens HitPay's payment page for a booking or a season parking purchase; once it closes, asks the
/// server to check the payment and returns the record as it is now (null if that check failed).
Future<Map<String, dynamic>?> payOnline(BuildContext context,
    {required String resource, required String event, required int id, required String url, required String returnPrefix}) async {
  await Navigator.of(context).push<void>(MaterialPageRoute(
      fullscreenDialog: true,
      builder: (_) => PaymentScreen(resource: resource, event: event, id: id, url: url, returnPrefix: returnPrefix)));
  try {
    return await Api.instance.post('/v1/$resource/$id/refresh/') as Map<String, dynamic>;
  } catch (_) {
    return null;
  }
}

class PaymentScreen extends StatefulWidget {
  const PaymentScreen({super.key, required this.resource, required this.event, required this.id, required this.url, required this.returnPrefix});
  /// API collection (`bookings`, `parking-permits`) and the live event type of the record being paid.
  final String resource;
  final String event;
  final int id;
  final String url;
  final String returnPrefix;
  @override
  State<PaymentScreen> createState() => _PaymentScreenState();
}

class _PaymentScreenState extends State<PaymentScreen> {
  late final WebViewController _web;
  bool _loading = true;
  bool _done = false;
  Timer? _poll;
  StreamSubscription? _events;

  @override
  void initState() {
    super.initState();
    _web = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onPageFinished: (_) {
          if (mounted) setState(() => _loading = false);
        },
        onNavigationRequest: (request) {
          // HitPay sends the resident back to our return page: the payment step is over.
          if (widget.returnPrefix.isNotEmpty && request.url.startsWith(widget.returnPrefix)) {
            _finish();
            return NavigationDecision.prevent;
          }
          return NavigationDecision.navigate;
        },
      ))
      ..loadRequest(Uri.parse(widget.url));
    // The webhook may confirm the payment first (e.g. PayNow paid from a banking app).
    _poll = Timer.periodic(const Duration(seconds: 5), (_) => _check());
    _events = Realtime.instance.events.listen((event) {
      if (event['type'] == widget.event && (event['data'] as Map?)?['id'] == widget.id && (event['data'] as Map)['status'] != 'pending_payment') {
        _finish();
      }
    });
  }

  Future<void> _check() async {
    try {
      final data = await Api.instance.get('/v1/${widget.resource}/${widget.id}/') as Map<String, dynamic>;
      if (data['status'] != 'pending_payment') _finish();
    } catch (_) {}
  }

  void _finish() {
    if (_done || !mounted) return;
    _done = true;
    Navigator.of(context).pop();
  }

  @override
  void dispose() {
    _poll?.cancel();
    _events?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('Payment'),
          leading: IconButton(icon: const Icon(Icons.close), onPressed: _finish, tooltip: 'Close'),
        ),
        body: Stack(children: [
          WebViewWidget(controller: _web),
          if (_loading) const Center(child: CircularProgressIndicator()),
        ]),
      );
}
