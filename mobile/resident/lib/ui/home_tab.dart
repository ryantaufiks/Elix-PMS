import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../calls.dart';
import '../models.dart';
import '../notifications.dart';
import '../realtime.dart';
import '../session.dart';
import '../theme.dart';
import 'access_screen.dart';
import 'activity_screen.dart';
import 'facilities_screen.dart';
import 'feedback_screen.dart';
import 'notifications_screen.dart';
import 'visitors_screen.dart';
import 'weather_badge.dart';
import 'widgets.dart';

/// Recent activity shown on the home screen; the rest is under "See all".
const _recent = 5;

class HomeTab extends StatefulWidget {
  const HomeTab({super.key});
  @override
  State<HomeTab> createState() => _HomeTabState();
}

class _HomeTabState extends State<HomeTab> {
  List<AccessEntry>? _activity;
  List<IntercomCall> _ringing = [];
  StreamSubscription? _sub;
  final _weather = GlobalKey<WeatherBadgeState>();

  @override
  void initState() {
    super.initState();
    _load();
    _sub = Realtime.instance.events.listen((event) {
      if (event['type'] == 'access_log' || event['type'] == 'intercom_call') _load();
      if (event['type'] == 'booking') NotificationCenter.instance.refresh();
    });
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    NotificationCenter.instance.refresh();
    _weather.currentState?.refresh();
    try {
      final logs = await Api.instance.list('/v1/access-logs/?page_size=$_recent');
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

  Future<void> _open(Widget screen) async {
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
    _load();
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
            // Two columns: logo, greeting, name and units on the left; the bell level with the logo and
            // the weather centred against the name and units on the right.
            child: IntrinsicHeight(
              child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    SizedBox(height: 40, child: Align(alignment: Alignment.centerLeft, child: Image.asset('assets/elix-logo.png', height: 26))),
                    const SizedBox(height: 12),
                    Text('$greeting,', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 16)),
                    Text(me.firstName.isEmpty ? me.displayName : me.firstName,
                        maxLines: 1, overflow: TextOverflow.ellipsis,
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
                const SizedBox(width: 12),
                Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  SizedBox(height: 40, child: Center(child: _Bell(onTap: () => _open(const NotificationsScreen())))),
                  Expanded(
                    child: Center(
                      child: me.residencies.isEmpty
                          ? const SizedBox.shrink()
                          : WeatherBadge(key: _weather, condominium: me.residencies.first.condominium),
                    ),
                  ),
                ]),
              ]),
            ),
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
          padding: const EdgeInsets.fromLTRB(16, 20, 16, 0),
          sliver: SliverGrid.count(
            crossAxisCount: 4,
            mainAxisSpacing: 10,
            crossAxisSpacing: 10,
            childAspectRatio: 0.82,
            children: [
              _MenuCard(icon: Icons.lock_open_rounded, label: 'Access', color: const Color(0xFF16A34A),
                  onTap: () => _open(const AccessScreen())),
              _MenuCard(icon: Icons.event_available_rounded, label: 'Facility', color: brandBlue,
                  onTap: () => _open(const FacilitiesScreen())),
              _MenuCard(icon: Icons.people_alt_rounded, label: 'Visitor', color: const Color(0xFF7C3AED),
                  onTap: () => _open(const VisitorsScreen())),
              _MenuCard(icon: Icons.star_rounded, label: 'Feedback', color: const Color(0xFFF59E0B),
                  onTap: () => _open(const FeedbackScreen())),
            ],
          ),
        ),
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(20, 24, 8, 8),
          sliver: SliverToBoxAdapter(
            child: Row(children: [
              Expanded(child: Text('Recent activity', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600))),
              if ((_activity?.length ?? 0) >= _recent)
                TextButton(onPressed: () => _open(const ActivityScreen()), child: const Text('See all')),
            ]),
          ),
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
              itemBuilder: (context, i) => ActivityTile(_activity![i]),
            ),
          ),
        const SliverToBoxAdapter(child: SizedBox(height: 24)),
      ]),
    );
  }
}

/// Bell with the number of new notifications.
class _Bell extends StatelessWidget {
  const _Bell({required this.onTap});
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: NotificationCenter.instance,
        builder: (context, _) {
          final center = NotificationCenter.instance;
          final unread = center.unread;
          return IconButton(
            tooltip: unread == 0 ? 'Notifications' : '$unread new notifications',
            onPressed: onTap,
            style: IconButton.styleFrom(backgroundColor: Colors.white.withValues(alpha: 0.1)),
            icon: Badge(
              isLabelVisible: unread > 0,
              backgroundColor: const Color(0xFFEF4444),
              label: Text(center.more ? '$unread+' : '$unread'),
              child: const Icon(Icons.notifications_none_rounded, color: Colors.white),
            ),
          );
        },
      );
}

class _MenuCard extends StatelessWidget {
  const _MenuCard({required this.icon, required this.label, required this.color, required this.onTap});
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Card(
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            Container(
              width: 46,
              height: 46,
              decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(14)),
              child: Icon(icon, color: color, size: 26),
            ),
            const SizedBox(height: 8),
            Text(label, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
          ]),
        ),
      );
}

/// One access-log entry (home screen and "See all").
class ActivityTile extends StatelessWidget {
  const ActivityTile(this.entry, {super.key});
  final AccessEntry entry;
  @override
  Widget build(BuildContext context) {
    final granted = entry.result == 'granted';
    final color = granted ? const Color(0xFF16A34A) : entry.result == 'denied' ? const Color(0xFFDC2626) : const Color(0xFFD97706);
    final icon = switch (entry.method) {
      'lpr' => Icons.directions_car,
      'qr' => Icons.qr_code_2,
      'intercom' => Icons.videocam,
      'app' => Icons.smartphone,
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
