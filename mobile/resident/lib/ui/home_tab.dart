import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../calls.dart';
import '../models.dart';
import '../realtime.dart';
import '../session.dart';
import '../theme.dart';
import 'widgets.dart';

class HomeTab extends StatefulWidget {
  const HomeTab({super.key});
  @override
  State<HomeTab> createState() => _HomeTabState();
}

class _HomeTabState extends State<HomeTab> {
  List<AccessEntry>? _activity;
  List<IntercomCall> _ringing = [];
  StreamSubscription? _sub;

  @override
  void initState() {
    super.initState();
    _load();
    _sub = Realtime.instance.events.listen((event) {
      if (event['type'] == 'access_log' || event['type'] == 'intercom_call') _load();
    });
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final logs = await Api.instance.list('/v1/access-logs/?page_size=20');
      final calls = await Api.instance.list('/v1/intercom-calls/?status=ringing');
      if (!mounted) return;
      setState(() {
        _activity = logs.map(AccessEntry.new).toList();
        _ringing = calls.map(IntercomCall.new).where((c) => c.isOpen).toList();
      });
    } catch (e) {
      if (mounted && _activity == null) setState(() => _activity = []);
    }
  }

  @override
  Widget build(BuildContext context) {
    final me = Session.instance.me!;
    final hour = DateTime.now().hour;
    final greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
    return RefreshIndicator(
      onRefresh: _load,
      child: CustomScrollView(slivers: [
        SliverToBoxAdapter(
          child: Container(
            padding: EdgeInsets.fromLTRB(20, MediaQuery.paddingOf(context).top + 20, 20, 28),
            decoration: const BoxDecoration(
              gradient: LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [Color(0xFF1B3B8F), navy, navyDeep]),
              borderRadius: BorderRadius.vertical(bottom: Radius.circular(28)),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Image.asset('assets/elix-logo.png', height: 26),
              const SizedBox(height: 24),
              Text('$greeting,', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 16)),
              Text(me.firstName.isEmpty ? me.displayName : me.firstName,
                  style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.w600)),
              const SizedBox(height: 16),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final r in me.residencies)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(20)),
                    child: Row(mainAxisSize: MainAxisSize.min, children: [
                      const Icon(Icons.apartment, size: 16, color: Colors.white70),
                      const SizedBox(width: 6),
                      Text(r.unitDisplay, style: const TextStyle(color: Colors.white)),
                    ]),
                  ),
              ]),
            ]),
          ),
        ),
        if (_ringing.isNotEmpty)
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
            sliver: SliverList.list(children: [
              for (final call in _ringing)
                Card(
                  color: brandBlue,
                  child: ListTile(
                    leading: const Icon(Icons.videocam, color: Colors.white),
                    title: Text('Visitor at ${call.kioskName}', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                    subtitle: Text(call.visitorName.isEmpty ? call.unitDisplay : call.visitorName, style: const TextStyle(color: Colors.white70)),
                    trailing: const Icon(Icons.chevron_right, color: Colors.white),
                    onTap: () => Calls.instance.answer(call.id),
                  ),
                ),
            ]),
          ),
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 8),
          sliver: SliverToBoxAdapter(child: Text('Recent activity', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600))),
        ),
        if (_activity == null)
          const SliverToBoxAdapter(child: Padding(padding: EdgeInsets.all(32), child: Center(child: CircularProgressIndicator())))
        else if (_activity!.isEmpty)
          const SliverToBoxAdapter(child: EmptyState(icon: Icons.history, text: 'Entries for your unit appear here.'))
        else
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            sliver: SliverList.separated(
              itemCount: _activity!.length,
              separatorBuilder: (_, _) => const SizedBox(height: 8),
              itemBuilder: (context, i) => _ActivityTile(_activity![i]),
            ),
          ),
        const SliverToBoxAdapter(child: SizedBox(height: 24)),
      ]),
    );
  }
}

class _ActivityTile extends StatelessWidget {
  const _ActivityTile(this.entry);
  final AccessEntry entry;
  @override
  Widget build(BuildContext context) {
    final granted = entry.result == 'granted';
    final color = granted ? const Color(0xFF16A34A) : entry.result == 'denied' ? const Color(0xFFDC2626) : const Color(0xFFD97706);
    final icon = switch (entry.method) {
      'lpr' => Icons.directions_car,
      'qr' => Icons.qr_code_2,
      'intercom' => Icons.videocam,
      _ => Icons.door_front_door_outlined,
    };
    final title = [entry.plate, entry.visitor].where((s) => s.isNotEmpty).join(' · ');
    return Card(
      child: ListTile(
        leading: CircleAvatar(backgroundColor: color.withValues(alpha: 0.12), child: Icon(icon, color: color, size: 20)),
        title: Text(title.isEmpty ? (methodLabel[entry.method] ?? entry.method) : title, maxLines: 1, overflow: TextOverflow.ellipsis),
        subtitle: Text('${granted ? 'Entered' : entry.result == 'denied' ? 'Refused' : 'Gate error'} · ${entry.gate}${entry.actor.isNotEmpty ? ' · ${entry.actor}' : ''}',
            maxLines: 1, overflow: TextOverflow.ellipsis),
        trailing: Text(timeAgo(entry.at), style: TextStyle(color: Theme.of(context).colorScheme.outline, fontSize: 12)),
      ),
    );
  }
}
