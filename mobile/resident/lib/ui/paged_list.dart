import 'package:flutter/material.dart';

import '../api.dart';
import 'widgets.dart';

/// A list from a paginated API endpoint, one page at a time with a pager underneath
/// ("‹  Page 2 of 5  ›"). Pull down to refresh the current page.
class PagedList<T> extends StatefulWidget {
  const PagedList({
    super.key,
    required this.path,
    required this.parse,
    required this.itemBuilder,
    required this.empty,
    this.pageSize = 10,
    this.padding = const EdgeInsets.fromLTRB(16, 12, 16, 24),
    this.spacing = 8,
    this.header = const [],
  });

  /// Endpoint with its filters, e.g. `/v1/visits/?state=on_site`; `page` and `page_size` are added.
  final String path;
  final T Function(Map<String, dynamic>) parse;
  final Widget Function(BuildContext, T) itemBuilder;
  final Widget empty;
  final int pageSize;
  final EdgeInsets padding;
  final double spacing;

  /// Widgets above the items (a form, a title), scrolled with them.
  final List<Widget> header;

  @override
  State<PagedList<T>> createState() => PagedListState<T>();
}

class PagedListState<T> extends State<PagedList<T>> with AutomaticKeepAliveClientMixin {
  final _scroll = ScrollController();
  List<T>? _items;
  int _page = 1;
  int _count = 0;
  bool _loading = false;

  @override
  bool get wantKeepAlive => true;

  int get _pages => (_count / widget.pageSize).ceil().clamp(1, 1 << 30);

  @override
  void initState() {
    super.initState();
    _load(1);
  }

  @override
  void didUpdateWidget(PagedList<T> oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.path != widget.path) _load(1);
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  /// Reload the current page (after the user changed something in the list).
  Future<void> reload() => _load(_page);

  Future<void> _load(int page) async {
    setState(() => _loading = true);
    try {
      final sep = widget.path.contains('?') ? '&' : '?';
      final data = await Api.instance.get('${widget.path}${sep}page=$page&page_size=${widget.pageSize}') as Map<String, dynamic>;
      final rows = (data['results'] as List).cast<Map<String, dynamic>>();
      if (!mounted) return;
      setState(() {
        _page = page;
        _count = data['count'] as int? ?? rows.length;
        _items = rows.map(widget.parse).toList();
      });
      if (_scroll.hasClients) _scroll.jumpTo(0);
    } on ApiException catch (e) {
      // A page that no longer exists (items were removed): go back to the last one.
      if (e.status == 404 && page > 1) return _load(page - 1);
      if (mounted) {
        setState(() => _items ??= []);
        showError(context, e);
      }
    } catch (e) {
      if (mounted) {
        setState(() => _items ??= []);
        showError(context, e);
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final items = _items;
    return RefreshIndicator(
      onRefresh: reload,
      child: ListView(controller: _scroll, padding: widget.padding, children: [
        ...widget.header,
        if (items == null)
          const Padding(padding: EdgeInsets.all(32), child: Center(child: CircularProgressIndicator()))
        else if (items.isEmpty)
          widget.empty
        else ...[
          for (var i = 0; i < items.length; i++)
            Padding(padding: EdgeInsets.only(top: i == 0 ? 0 : widget.spacing), child: widget.itemBuilder(context, items[i])),
          if (_count > widget.pageSize) _Pager(page: _page, pages: _pages, count: _count, loading: _loading, onPage: _load),
        ],
      ]),
    );
  }
}

class _Pager extends StatelessWidget {
  const _Pager({required this.page, required this.pages, required this.count, required this.loading, required this.onPage});
  final int page;
  final int pages;
  final int count;
  final bool loading;
  final ValueChanged<int> onPage;

  @override
  Widget build(BuildContext context) {
    final outline = Theme.of(context).colorScheme.outline;
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Row(children: [
        IconButton.filledTonal(
          tooltip: 'Previous page',
          onPressed: loading || page <= 1 ? null : () => onPage(page - 1),
          icon: const Icon(Icons.chevron_left_rounded),
        ),
        Expanded(
          child: Column(children: [
            Text('Page $page of $pages', style: const TextStyle(fontWeight: FontWeight.w600)),
            Text('$count items', style: TextStyle(color: outline, fontSize: 12)),
          ]),
        ),
        IconButton.filledTonal(
          tooltip: 'Next page',
          onPressed: loading || page >= pages ? null : () => onPage(page + 1),
          icon: const Icon(Icons.chevron_right_rounded),
        ),
      ]),
    );
  }
}
