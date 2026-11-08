import 'package:flutter/material.dart';

import '../api.dart';
import '../models.dart';
import 'home_tab.dart';
import 'widgets.dart';

/// Every access to the resident's units, newest first, loaded page by page.
class ActivityScreen extends StatefulWidget {
  const ActivityScreen({super.key});
  @override
  State<ActivityScreen> createState() => _ActivityScreenState();
}

class _ActivityScreenState extends State<ActivityScreen> {
  final _items = <AccessEntry>[];
  int _page = 0;
  bool _more = true;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _next();
  }

  Future<void> _reload() async {
    setState(() {
      _items.clear();
      _page = 0;
      _more = true;
    });
    await _next();
  }

  Future<void> _next() async {
    if (_loading || !_more) return;
    setState(() => _loading = true);
    try {
      final data = await Api.instance.get('/v1/access-logs/?page_size=30&page=${_page + 1}') as Map<String, dynamic>;
      final rows = (data['results'] as List).cast<Map<String, dynamic>>();
      setState(() {
        _page += 1;
        _items.addAll(rows.map(AccessEntry.new));
        _more = data['next'] != null;
      });
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Activity')),
        body: RefreshIndicator(
          onRefresh: _reload,
          child: NotificationListener<ScrollNotification>(
            onNotification: (n) {
              if (n.metrics.pixels > n.metrics.maxScrollExtent - 300) _next();
              return false;
            },
            child: _items.isEmpty && !_loading
                ? ListView(children: const [EmptyState(icon: Icons.history, text: 'Entries for your unit appear here.')])
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                    itemCount: _items.length + (_more ? 1 : 0),
                    separatorBuilder: (_, _) => const SizedBox(height: 8),
                    itemBuilder: (context, i) => i < _items.length
                        ? ActivityTile(_items[i])
                        : const Padding(padding: EdgeInsets.all(16), child: Center(child: CircularProgressIndicator())),
                  ),
          ),
        ),
      );
}
