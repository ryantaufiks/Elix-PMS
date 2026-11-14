import 'package:flutter/material.dart';

import '../models.dart';
import '../notifications.dart';
import 'paged_list.dart';
import 'widgets.dart';

/// Everything new at the resident's units in the last 30 days. Opening it marks all as read.
class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});
  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  // What counted as new when the screen opened, so new items stay highlighted while it is shown.
  final DateTime? _seenAt = NotificationCenter.instance.seenAt;

  @override
  void initState() {
    super.initState();
    NotificationCenter.instance.markAllRead();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Notifications')),
        body: PagedList<NotificationItem>(
          path: '/v1/notifications/',
          parse: NotificationItem.new,
          empty: const EmptyState(icon: Icons.notifications_none_rounded, text: 'Visitors, gate entries, bookings and replies from the management appear here.'),
          itemBuilder: (context, n) => NotificationTile(n, isNew: _seenAt == null || n.at.isAfter(_seenAt)),
        ),
      );
}

const _looks = <String, (IconData, Color)>{
  'visit_in': (Icons.person_pin_circle_rounded, Color(0xFF7C3AED)),
  'visit_out': (Icons.logout_rounded, Color(0xFF64748B)),
  'gate_open': (Icons.lock_open_rounded, Color(0xFF16A34A)),
  'gate_denied': (Icons.block_rounded, Color(0xFFDC2626)),
  'call_missed': (Icons.phone_missed_rounded, Color(0xFFD97706)),
  'booking_confirmed': (Icons.event_available_rounded, Color(0xFF2F6FFF)),
  'booking_cancelled': (Icons.event_busy_rounded, Color(0xFF64748B)),
  'booking_expired': (Icons.timer_off_rounded, Color(0xFFD97706)),
  'feedback_reply': (Icons.forum_rounded, Color(0xFFF59E0B)),
  'vehicle_expiring': (Icons.directions_car_rounded, Color(0xFFD97706)),
  'vehicle_expired': (Icons.no_crash_rounded, Color(0xFFDC2626)),
};

class NotificationTile extends StatelessWidget {
  const NotificationTile(this.item, {super.key, this.isNew = false});
  final NotificationItem item;
  final bool isNew;

  @override
  Widget build(BuildContext context) {
    final (icon, color) = _looks[item.kind] ?? (Icons.notifications_rounded, const Color(0xFF2F6FFF));
    final outline = Theme.of(context).colorScheme.outline;
    return Card(
      color: isNew ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.06) : null,
      child: ListTile(
        leading: CircleAvatar(backgroundColor: color.withValues(alpha: 0.12), child: Icon(icon, color: color, size: 20)),
        title: Text(item.title, maxLines: 1, overflow: TextOverflow.ellipsis,
            style: TextStyle(fontWeight: isNew ? FontWeight.w700 : FontWeight.w500)),
        subtitle: item.body.isEmpty ? null : Text(item.body, maxLines: 2, overflow: TextOverflow.ellipsis),
        trailing: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.end, children: [
          Text(timeAgo(item.at), style: TextStyle(color: outline, fontSize: 12)),
          if (isNew) ...[
            const SizedBox(height: 6),
            Container(width: 8, height: 8, decoration: BoxDecoration(color: Theme.of(context).colorScheme.primary, shape: BoxShape.circle)),
          ],
        ]),
      ),
    );
  }
}
