import 'package:flutter/material.dart';

import '../api.dart';
import '../models.dart';
import '../session.dart';
import 'paged_list.dart';
import 'widgets.dart';

/// Rate the estate's services (1–5 stars) and read the management's replies.
class FeedbackScreen extends StatefulWidget {
  const FeedbackScreen({super.key});
  @override
  State<FeedbackScreen> createState() => _FeedbackScreenState();
}

class _FeedbackScreenState extends State<FeedbackScreen> {
  final _list = GlobalKey<PagedListState<FeedbackItem>>();
  int _rating = 0;
  String _category = 'security';
  final _comment = TextEditingController();
  bool _sending = false;

  @override
  void dispose() {
    _comment.dispose();
    super.dispose();
  }

  void _load() => _list.currentState?.reload();

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
      body: PagedList<FeedbackItem>(
        key: _list,
        path: '/v1/feedback/',
        parse: FeedbackItem.new,
        padding: const EdgeInsets.all(16),
        empty: const EmptyState(icon: Icons.star_outline, text: 'Your ratings and the replies appear here.'),
        itemBuilder: (context, f) => _FeedbackCard(f),
        header: [
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
        ],
      ),
    );
  }
}

class _FeedbackCard extends StatelessWidget {
  const _FeedbackCard(this.f);
  final FeedbackItem f;

  @override
  Widget build(BuildContext context) {
    final outline = Theme.of(context).colorScheme.outline;
    return Card(
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
    );
  }
}

class _Stars extends StatelessWidget {
  const _Stars({required this.value, this.size = 24, this.onChanged});
  final int value;
  final double size;
  final ValueChanged<int>? onChanged;

  @override
  Widget build(BuildContext context) {
    final row = Row(mainAxisSize: MainAxisSize.min, children: [
      for (var i = 1; i <= 5; i++)
        Semantics(
          button: onChanged != null,
          selected: onChanged != null && i == value,
          label: i == 1 ? '1 star' : '$i stars',
          onTap: onChanged == null ? null : () => onChanged!(i),
          excludeSemantics: true,
          child: GestureDetector(
            onTap: onChanged == null ? null : () => onChanged!(i),
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: onChanged == null ? 0 : 4),
              child: Icon(i <= value ? Icons.star_rounded : Icons.star_outline_rounded, size: size,
                  color: i <= value ? const Color(0xFFF59E0B) : Theme.of(context).colorScheme.outline),
            ),
          ),
        ),
    ]);
    // A rating on a past review is read as one phrase, not five unlabelled icons.
    return onChanged == null ? Semantics(label: '$value out of 5 stars', excludeSemantics: true, child: row) : row;
  }
}
