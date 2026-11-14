import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../api.dart';
import '../models.dart';
import '../realtime.dart';
import '../session.dart';
import 'paged_list.dart';
import 'payment_screen.dart';
import 'widgets.dart';

const facilityIcons = <String, IconData>{
  'event': Icons.event_available_rounded,
  'outdoor_grill': Icons.outdoor_grill_rounded,
  'meeting_room': Icons.meeting_room_rounded,
  'sports_tennis': Icons.sports_tennis_rounded,
  'sports_basketball': Icons.sports_basketball_rounded,
  'fitness_center': Icons.fitness_center_rounded,
  'pool': Icons.pool_rounded,
  'celebration': Icons.celebration_rounded,
  'spa': Icons.spa_rounded,
  'sports_esports': Icons.sports_esports_rounded,
  'local_parking': Icons.local_parking_rounded,
};

final _day = DateFormat('EEE');
final _dayNumber = DateFormat('d MMM');
final _hm = DateFormat('HH:mm');
String _money(double v, [String currency = 'SGD']) => '$currency ${v.toStringAsFixed(2)}';

/// Facilities to book, and the unit's bookings.
class FacilitiesScreen extends StatefulWidget {
  const FacilitiesScreen({super.key});
  @override
  State<FacilitiesScreen> createState() => _FacilitiesScreenState();
}

class _FacilitiesScreenState extends State<FacilitiesScreen> {
  final _bookings = GlobalKey<_MyBookingsState>();

  @override
  Widget build(BuildContext context) => DefaultTabController(
        length: 2,
        child: Scaffold(
          appBar: AppBar(
            title: const Text('Facilities'),
            bottom: const TabBar(tabs: [Tab(text: 'Book'), Tab(text: 'My bookings')]),
          ),
          body: TabBarView(children: [
            _FacilityList(onBooked: () {
              _bookings.currentState?._load();
              DefaultTabController.of(context).animateTo(1);
            }),
            _MyBookings(key: _bookings),
          ]),
        ),
      );
}

class _FacilityList extends StatelessWidget {
  const _FacilityList({required this.onBooked});
  final VoidCallback onBooked;

  @override
  Widget build(BuildContext context) {
    final outline = Theme.of(context).colorScheme.outline;
    return PagedList<Facility>(
      path: '/v1/facilities/?is_active=true',
      parse: Facility.new,
      spacing: 12,
      empty: const EmptyState(icon: Icons.event_busy, text: 'No facilities can be booked yet.'),
      itemBuilder: (context, f) {
        return Card(
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: () async {
              final booked = await Navigator.of(context).push<bool>(MaterialPageRoute(builder: (_) => BookFacilityScreen(facility: f)));
              if (booked == true) onBooked();
            },
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (f.hasImage) SizedBox(height: 140, width: double.infinity, child: AuthImage('/v1/facilities/${f.id}/photo/', semanticLabel: 'Photo of ${f.name}')),
              ListTile(
                contentPadding: const EdgeInsets.fromLTRB(16, 8, 12, 8),
                leading: CircleAvatar(
                  backgroundColor: Theme.of(context).colorScheme.primary.withValues(alpha: 0.12),
                  child: Icon(facilityIcons[f.icon] ?? Icons.event_available_rounded, color: Theme.of(context).colorScheme.primary),
                ),
                title: Text(f.name, style: const TextStyle(fontWeight: FontWeight.w600)),
                subtitle: Text([f.location, '${f.opensAt}–${f.closesAt}'].where((s) => s.isNotEmpty).join(' · '),
                    style: TextStyle(color: outline)),
                trailing: Text(f.priceLabel, style: const TextStyle(fontWeight: FontWeight.w600)),
              ),
            ]),
          ),
        );
      },
    );
  }
}

/// Pick a day and consecutive slots, then book (and pay when the facility is not free).
class BookFacilityScreen extends StatefulWidget {
  const BookFacilityScreen({super.key, required this.facility});
  final Facility facility;
  @override
  State<BookFacilityScreen> createState() => _BookFacilityScreenState();
}

class _BookFacilityScreenState extends State<BookFacilityScreen> {
  late final List<DateTime> _days;
  late DateTime _date;
  List<Slot>? _slots;
  bool _open = true;
  int? _first;
  int _count = 0;
  int _guests = 1;
  late int? _unit;
  bool _booking = false;
  final _notes = TextEditingController();

  Facility get f => widget.facility;

  List<Residency> get _units => Session.instance.me!.residencies.where((r) => r.condominium == f.condominium).toList();

  @override
  void initState() {
    super.initState();
    final today = DateTime.now();
    _days = [for (var i = 0; i <= f.advanceDays; i++) DateTime(today.year, today.month, today.day + i)];
    _date = _days.first;
    _unit = _units.isEmpty ? null : _units.first.unit;
    _load();
  }

  @override
  void dispose() {
    _notes.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _slots = null;
      _first = null;
      _count = 0;
    });
    try {
      final data = await Api.instance.get('/v1/facilities/${f.id}/availability/?date=${DateFormat('yyyy-MM-dd').format(_date)}') as Map<String, dynamic>;
      if (!mounted) return;
      setState(() {
        _open = data['open'] as bool? ?? false;
        _slots = (data['slots'] as List).cast<Map<String, dynamic>>().map(Slot.new).toList();
      });
    } catch (e) {
      if (mounted) {
        setState(() => _slots = []);
        showError(context, e);
      }
    }
  }

  void _tap(int i) {
    setState(() {
      if (_first != null && i == _first! + _count && _count < f.maxSlots && _slots![i].available) {
        _count += 1; // Extend the selection by the next slot.
      } else if (_first != null && i >= _first! && i < _first! + _count) {
        _count = i - _first!; // Shrink back to before the tapped slot.
        if (_count == 0) _first = null;
      } else {
        _first = i;
        _count = 1;
      }
    });
  }

  double get _total => f.pricePerSlot * _count + (_count > 0 ? f.deposit : 0);

  Future<void> _book() async {
    if (_first == null) return;
    setState(() => _booking = true);
    try {
      final data = await Api.instance.post('/v1/bookings/', {
        'facility': f.id,
        'unit': _unit,
        'starts_at': _slots![_first!].raw,
        'slots': _count,
        'guests': _guests,
        'notes': _notes.text.trim(),
      }) as Map<String, dynamic>;
      if (!mounted) return;
      final booking = Booking((data['booking'] as Map).cast<String, dynamic>());
      final url = data['payment_url'] as String? ?? '';
      if (url.isEmpty) {
        showMessage(context, '${f.name} booked for ${formatDateTime(booking.startsAt)}.');
        Navigator.of(context).pop(true);
        return;
      }
      final paid = await payForBooking(context, booking.id, url, data['return_url_prefix'] as String? ?? '');
      if (!mounted) return;
      showMessage(context, paid ? 'Payment received. ${f.name} is booked.' : 'Booking not paid yet. You can pay from My bookings before it expires.');
      Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) {
        showError(context, e);
        _load();
      }
    } finally {
      if (mounted) setState(() => _booking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final outline = scheme.outline;
    return Scaffold(
      appBar: AppBar(title: Text(f.name)),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
          child: FilledButton(
            onPressed: _first == null || _booking || _unit == null ? null : _book,
            child: Text(_booking
                ? 'Booking…'
                : _first == null
                    ? 'Choose a time'
                    : f.isPaid
                        ? 'Book & pay ${_money(_total)}'
                        : 'Book ${_hm.format(_slots![_first!].startsAt)}–${_hm.format(_slots![_first! + _count - 1].endsAt)}'),
          ),
        ),
      ),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        if (f.description.isNotEmpty) Text(f.description),
        const SizedBox(height: 6),
        Text([if (f.location.isNotEmpty) f.location, 'Up to ${f.capacity} people', f.priceLabel,
              if (f.deposit > 0) '${_money(f.deposit)} refundable deposit'].join(' · '),
            style: TextStyle(color: outline)),
        if (_units.length > 1) ...[
          const SizedBox(height: 12),
          DropdownButtonFormField<int>(
            initialValue: _unit,
            decoration: const InputDecoration(labelText: 'Book for unit'),
            items: [for (final r in _units) DropdownMenuItem(value: r.unit, child: Text(r.unitDisplay))],
            onChanged: (v) => setState(() => _unit = v),
          ),
        ],
        const SizedBox(height: 16),
        SizedBox(
          height: 72,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: _days.length,
            separatorBuilder: (_, _) => const SizedBox(width: 8),
            itemBuilder: (context, i) {
              final d = _days[i];
              final selected = d == _date;
              void pick() {
                setState(() => _date = d);
                _load();
              }
              return Semantics(
                button: true,
                selected: selected,
                label: i == 0 ? 'Today, ${_dayNumber.format(d)}' : '${_day.format(d)} ${_dayNumber.format(d)}',
                onTap: pick,
                excludeSemantics: true,
                child: GestureDetector(
                  onTap: pick,
                  child: Container(
                    width: 62,
                    decoration: BoxDecoration(
                      color: selected ? scheme.primary : scheme.surface,
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: selected ? scheme.primary : scheme.outlineVariant),
                    ),
                    child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                      Text(i == 0 ? 'Today' : _day.format(d), style: TextStyle(fontSize: 12, color: selected ? scheme.onPrimary.withValues(alpha: 0.75) : outline)),
                      const SizedBox(height: 2),
                      Text(_dayNumber.format(d), style: TextStyle(fontWeight: FontWeight.w600, color: selected ? scheme.onPrimary : null)),
                    ]),
                  ),
                ),
              );
            },
          ),
        ),
        const SizedBox(height: 16),
        if (_slots == null)
          const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator()))
        else if (!_open || _slots!.isEmpty)
          const EmptyState(icon: Icons.event_busy, text: 'Closed on this day.')
        else ...[
          Text(f.maxSlots > 1 ? 'Tap a start time, then the next slots to book up to ${f.maxSlots}.' : 'Tap a time to book it.',
              style: TextStyle(color: outline, fontSize: 13)),
          const SizedBox(height: 10),
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (var i = 0; i < _slots!.length; i++)
              ChoiceChip(
                label: Text('${_hm.format(_slots![i].startsAt)}–${_hm.format(_slots![i].endsAt)}'),
                selected: _first != null && i >= _first! && i < _first! + _count,
                onSelected: _slots![i].available ? (_) => _tap(i) : null,
              ),
          ]),
        ],
        const SizedBox(height: 20),
        Row(children: [
          const Expanded(child: Text('People', style: TextStyle(fontWeight: FontWeight.w500))),
          IconButton(onPressed: _guests > 1 ? () => setState(() => _guests -= 1) : null, icon: const Icon(Icons.remove_circle_outline)),
          Text('$_guests', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          IconButton(onPressed: _guests < f.capacity ? () => setState(() => _guests += 1) : null, icon: const Icon(Icons.add_circle_outline)),
        ]),
        TextField(controller: _notes, maxLength: 255, decoration: const InputDecoration(hintText: 'Note for the management (optional)')),
        if (f.rules.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text('Rules', style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text(f.rules, style: TextStyle(color: outline)),
        ],
        const SizedBox(height: 8),
        Text('You can cancel up to ${f.cancelHours} hours before the start.', style: TextStyle(color: outline, fontSize: 13)),
      ]),
    );
  }
}

/// Opens HitPay's payment page; returns true once the booking is confirmed.
Future<bool> payForBooking(BuildContext context, int bookingId, String url, String returnPrefix) async =>
    (await payOnline(context, resource: 'bookings', event: 'booking', id: bookingId, url: url, returnPrefix: returnPrefix))?['status'] ==
    'confirmed';

class _MyBookings extends StatefulWidget {
  const _MyBookings({super.key});
  @override
  State<_MyBookings> createState() => _MyBookingsState();
}

class _MyBookingsState extends State<_MyBookings> {
  final _list = GlobalKey<PagedListState<Booking>>();
  StreamSubscription? _events;

  @override
  void initState() {
    super.initState();
    _load();
    _events = Realtime.instance.events.listen((event) {
      if (event['type'] == 'booking') _load();
    });
  }

  @override
  void dispose() {
    _events?.cancel();
    super.dispose();
  }

  void _load() => _list.currentState?.reload();

  /// The booking's QR: scanned at the kiosk's Facilities from 15 minutes before the start.
  Future<void> _showQr(Booking b) => showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(b.facilityName),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            Text('${DateFormat('EEE d MMM, HH:mm').format(b.startsAt)} – ${_hm.format(b.endsAt)}'),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(12)),
              child: SizedBox(width: 220, height: 220,
                  child: AuthImage('/v1/bookings/${b.id}/qr/', fit: BoxFit.contain, semanticLabel: 'Booking check-in QR code')),
            ),
            const SizedBox(height: 12),
            const Text('Show this at the kiosk: Facilities → Check in to my booking. It works from 15 minutes before the start.',
                textAlign: TextAlign.center),
          ]),
          actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
        ),
      );

  Future<void> _pay(Booking b) async {
    try {
      final data = await Api.instance.post('/v1/bookings/${b.id}/pay/') as Map<String, dynamic>;
      if (!mounted) return;
      final paid = await payForBooking(context, b.id, data['payment_url'] as String, data['return_url_prefix'] as String? ?? '');
      if (mounted && paid) showMessage(context, 'Payment received. ${b.facilityName} is booked.');
    } catch (e) {
      if (mounted) showError(context, e);
    }
    _load();
  }

  Future<void> _cancel(Booking b) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Cancel ${b.facilityName}?'),
        content: Text(b.paymentStatus == 'paid'
            ? 'The management office refunds paid bookings; it may take a few days.'
            : 'The time slot will be released.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Cancel booking')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await Api.instance.post('/v1/bookings/${b.id}/cancel/');
      if (mounted) showMessage(context, 'Booking cancelled.');
    } catch (e) {
      if (mounted) showError(context, e);
    }
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final outline = Theme.of(context).colorScheme.outline;
    return PagedList<Booking>(
      key: _list,
      path: '/v1/bookings/?ordering=-starts_at',
      parse: Booking.new,
      empty: const EmptyState(icon: Icons.event_note, text: 'Your bookings appear here.'),
      itemBuilder: (context, b) {
        final color = switch (b.status) {
          'confirmed' => const Color(0xFF16A34A),
          'pending_payment' => const Color(0xFFD97706),
          _ => const Color(0xFF64748B),
        };
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Icon(facilityIcons[b.facilityIcon] ?? Icons.event_available_rounded, color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 10),
                Expanded(child: Text(b.facilityName, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16))),
                StatusChip(b.statusDisplay, color: color),
              ]),
              const SizedBox(height: 8),
              Text('${formatDateTime(b.startsAt)} – ${_hm.format(b.endsAt)} · ${b.guests} people'),
              Text(
                [b.unitDisplay, if (b.amount > 0) '${_money(b.amount, b.currency)} (${b.paymentStatusDisplay.toLowerCase()})'].join(' · '),
                style: TextStyle(color: outline, fontSize: 13),
              ),
              if (b.cancelReason.isNotEmpty) Text(b.cancelReason, style: TextStyle(color: outline, fontSize: 13)),
              if (b.checkedInAt != null)
                Text('Checked in ${_hm.format(b.checkedInAt!)}', style: const TextStyle(color: Color(0xFF15803D), fontSize: 13)),
              if (b.awaitingPayment || b.canCancel || b.hasQr)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Row(mainAxisAlignment: MainAxisAlignment.end, children: [
                    if (b.canCancel) TextButton(onPressed: () => _cancel(b), child: const Text('Cancel')),
                    if (b.hasQr) ...[
                      const SizedBox(width: 8),
                      FilledButton.icon(
                        style: FilledButton.styleFrom(minimumSize: const Size(0, 40)),
                        onPressed: () => _showQr(b),
                        icon: const Icon(Icons.qr_code_2_rounded, size: 20),
                        label: const Text('Check-in QR'),
                      ),
                    ],
                    if (b.awaitingPayment) ...[
                      const SizedBox(width: 8),
                      FilledButton(
                        style: FilledButton.styleFrom(minimumSize: const Size(0, 40)),
                        onPressed: () => _pay(b),
                        child: const Text('Pay now'),
                      ),
                    ],
                  ]),
                ),
            ]),
          ),
        );
      },
    );
  }
}
