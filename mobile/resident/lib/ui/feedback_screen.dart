import 'package:flutter/material.dart';

import '../api.dart';
import '../models.dart';
import '../session.dart';
import 'widgets.dart';

/// Rate the estate's services (1–5 stars) and read the management's replies.
class FeedbackScreen extends StatefulWidget {
  const FeedbackScreen({super.key});
  @override
  State<FeedbackScreen> createState() => _FeedbackScreenState();
}

class _FeedbackScreenState extends State<FeedbackScreen> {
  List<FeedbackItem>? _items;
  int _rating = 0;
  String _category = 'security';
  final _comment = TextEditingController();
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _comment.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final rows = await Api.instance.list('/v1/feedback/?page_size=50');
      if (mounted) setState(() => _items = rows.map(FeedbackItem.new).toList());
    } catch (e) {
      if (mounted) setState(() => _items = []);
    }
  }

  Future<void> _send() async {
    if (_rating == 0) {
      showMessage(context, 'Tap the stars to rate.');
      return;
    }
    setState(() => _sending = true);
    try {
      final unit = Session.instance.me!.residencies.first.unit;
      await Api.instance.post('/v1/feedback/', {'unit': unit, 'rating': _rating, 'category': _category, 'comment': _comment.text.trim()});
      if (!mounted) return;
      FocusScope.of(context).unfocus();
      setState(() {
        _rating = 0;
        _comment.clear();
      });
      showMessage(context, 'Thank you for your feedback!');
      _load();
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final outline = Theme.of(context).colorScheme.outline;
    return Scaffold(
      appBar: AppBar(title: const Text('Feedback')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(padding: const EdgeInsets.all(16), children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('How are we doing?', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text('Rate a service. The management office reads every rating.', style: TextStyle(color: outline)),
                const SizedBox(height: 12),
                Center(child: _Stars(value: _rating, size: 40, onChanged: (v) => setState(() => _rating = v))),
                const SizedBox(height: 12),
                Wrap(spacing: 8, runSpacing: 8, children: [
                  for (final e in feedbackCategories.entries)
                    ChoiceChip(label: Text(e.value), selected: _category == e.key, onSelected: (_) => setState(() => _category = e.key)),
                ]),
                const SizedBox(height: 12),
                TextField(controller: _comment, maxLines: 4, maxLength: 2000,
                    decoration: const InputDecoration(hintText: 'Tell us more (optional)')),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(onPressed: _sending ? null : _send, child: Text(_sending ? 'Sending…' : 'Send feedback')),
                ),
              ]),
            ),
          ),
          const SizedBox(height: 24),
          Text('Your feedback', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          if (_items == null)
            const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator()))
          else if (_items!.isEmpty)
            const EmptyState(icon: Icons.star_outline, text: 'Your ratings and the replies appear here.')
          else
            for (final f in _items!)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Card(
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Row(children: [
                        _Stars(value: f.rating, size: 18),
                        const SizedBox(width: 8),
                        Expanded(child: Text(f.category, style: TextStyle(color: outline))),
                        StatusChip(f.statusDisplay, color: f.status == 'resolved' ? const Color(0xFF16A34A) : const Color(0xFF2F6FFF)),
                      ]),
                      if (f.comment.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 8), child: Text(f.comment)),
                      if (f.reply.isNotEmpty)
                        Container(
                          margin: const EdgeInsets.only(top: 10),
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.06),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text('Reply from ${f.repliedBy.isEmpty ? 'management' : f.repliedBy}', style: TextStyle(color: outline, fontSize: 12)),
                            const SizedBox(height: 2),
                            Text(f.reply),
                          ]),
                        ),
                      Padding(padding: const EdgeInsets.only(top: 8), child: Text(timeAgo(f.createdAt), style: TextStyle(color: outline, fontSize: 12))),
                    ]),
                  ),
                ),
              ),
        ]),
      ),
    );
  }
}

class _Stars extends StatelessWidget {
  const _Stars({required this.value, this.size = 24, this.onChanged});
  final int value;
  final double size;
  final ValueChanged<int>? onChanged;

  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        for (var i = 1; i <= 5; i++)
          GestureDetector(
            onTap: onChanged == null ? null : () => onChanged!(i),
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: onChanged == null ? 0 : 4),
              child: Icon(i <= value ? Icons.star_rounded : Icons.star_outline_rounded, size: size,
                  color: i <= value ? const Color(0xFFF59E0B) : Theme.of(context).colorScheme.outline),
            ),
          ),
      ]);
}
