import 'package:flutter/material.dart';

import '../models.dart';
import 'paged_list.dart';
import 'widgets.dart';

/// Visitors to the resident's units: who is on site now, and past visits with check-in and check-out times.
class VisitorsScreen extends StatelessWidget {
  const VisitorsScreen({super.key});

  @override
  Widget build(BuildContext context) => DefaultTabController(
        length: 2,
        child: Scaffold(
          appBar: AppBar(
            title: const Text('Visitors'),
            bottom: const TabBar(tabs: [Tab(text: 'On going'), Tab(text: 'History')]),
          ),
          body: const TabBarView(children: [_VisitList(onSite: true), _VisitList(onSite: false)]),
        ),
      );
}

class _VisitList extends StatelessWidget {
  const _VisitList({required this.onSite});
  final bool onSite;

  @override
  Widget build(BuildContext context) => PagedList<Visit>(
        path: onSite ? '/v1/visits/?state=on_site' : '/v1/visits/?ordering=-created_at',
        parse: Visit.new,
        itemBuilder: (context, visit) => _VisitCard(visit),
        empty: EmptyState(icon: Icons.people_outline, text: onSite ? 'No visitors on site for your unit.' : 'No visits yet.'),
      );
}

class _VisitCard extends StatelessWidget {
  const _VisitCard(this.visit);
  final Visit visit;

  @override
  Widget build(BuildContext context) {
    final outline = Theme.of(context).colorScheme.outline;
    final (label, color) = switch (visit.state) {
      'on_site' => ('On site', const Color(0xFF16A34A)),
      'checked_out' => ('Left', const Color(0xFF64748B)),
      _ => ('Not checked out', const Color(0xFFD97706)),
    };
    final details = [visit.purpose, visit.company, visit.plate].where((s) => s.isNotEmpty).join(' · ');
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text(visit.visitorName, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16))),
            StatusChip(label, color: color),
          ]),
          if (details.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 2), child: Text(details, style: TextStyle(color: outline))),
          const SizedBox(height: 10),
          Row(children: [
            Expanded(child: _Time(label: 'Check-in', value: formatDateTime(visit.checkIn))),
            Expanded(child: _Time(label: 'Check-out', value: visit.checkOut == null ? '—' : formatDateTime(visit.checkOut!))),
          ]),
          const SizedBox(height: 6),
          Text('Pass ${visit.passNumber} · ${visit.source} · ${visit.unitDisplay}', style: TextStyle(color: outline, fontSize: 12)),
        ]),
      ),
    );
  }
}

class _Time extends StatelessWidget {
  const _Time({required this.label, required this.value});
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: TextStyle(color: Theme.of(context).colorScheme.outline, fontSize: 12)),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w500)),
      ]);
}
