import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../api.dart';
import '../models.dart';
import '../session.dart';
import 'paged_list.dart';
import 'payment_screen.dart';
import 'widgets.dart';

class VehiclesTab extends StatefulWidget {
  const VehiclesTab({super.key});
  @override
  State<VehiclesTab> createState() => _VehiclesTabState();
}

class _VehiclesTabState extends State<VehiclesTab> {
  final _list = GlobalKey<PagedListState<Vehicle>>();
  ParkingOffer? _offer;

  @override
  void initState() {
    super.initState();
    _loadOffer();
  }

  Future<void> _loadOffer() async {
    final residencies = Session.instance.me?.residencies ?? const [];
    if (residencies.isEmpty) return;
    try {
      final data = await Api.instance.get('/v1/parking-permits/offer/?condominium=${residencies.first.condominium}');
      if (mounted) setState(() => _offer = ParkingOffer(data as Map<String, dynamic>));
    } catch (_) {}
  }

  void _load() => _list.currentState?.reload();

  /// Buy season parking, or renew a plate's pass ([vehicle]).
  Future<void> _seasonParking([Vehicle? vehicle]) async {
    final offer = _offer;
    if (offer == null) return;
    final bought = await showModalBottomSheet<bool>(
        context: context, isScrollControlled: true, builder: (_) => _SeasonParkingSheet(offer: offer, vehicle: vehicle));
    if (bought == true) _load();
    _loadOffer();
  }

  Future<void> _add() async {
    final added = await showModalBottomSheet<bool>(context: context, isScrollControlled: true, builder: (_) => const _AddVehicleSheet());
    if (added == true) _load();
  }

  Future<void> _remove(Vehicle v) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Remove ${v.plate}?'),
        content: const Text('The barrier will no longer open automatically for this car.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Remove')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await Api.instance.delete('/v1/vehicles/${v.id}/');
      _load();
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Vehicles'), actions: [
          if (_offer?.enabled == true)
            TextButton.icon(onPressed: () => _seasonParking(), icon: const Icon(Icons.local_parking_rounded), label: const Text('Season parking')),
        ]),
        floatingActionButton: FloatingActionButton.extended(onPressed: _add, icon: const Icon(Icons.add), label: const Text('Add vehicle')),
        body: PagedList<Vehicle>(
          key: _list,
          path: '/v1/vehicles/?is_active=true',
          parse: Vehicle.new,
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
          empty: const EmptyState(icon: Icons.directions_car_outlined, text: 'Register your car so the barrier opens automatically.'),
          itemBuilder: (context, v) {
            return Card(
              child: ListTile(
                leading: const CircleAvatar(child: Icon(Icons.directions_car)),
                title: Text(v.plate, style: const TextStyle(fontWeight: FontWeight.w700, letterSpacing: 1)),
                subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text([v.description, v.unitDisplay].where((s) => s.isNotEmpty).join(' · ')),
                  if (v.kind != 'resident' || v.validUntil != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Wrap(spacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
                        Text([v.kind == 'resident' ? '' : v.kindDisplay,
                              if (v.validUntil != null) 'until ${DateFormat('d MMM y').format(v.validUntil!)}'].where((s) => s.isNotEmpty).join(' · ')),
                        if (v.status == 'expiring') const StatusChip('Ends soon', color: Color(0xFFB45309)),
                        if (v.status == 'expired') const StatusChip('Expired', color: Color(0xFFDC2626)),
                      ]),
                    ),
                  if (v.kind == 'season' && _offer?.enabled == true)
                    Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton.icon(
                          onPressed: () => _seasonParking(v), icon: const Icon(Icons.autorenew_rounded, size: 18), label: const Text('Renew')),
                    ),
                ]),
                trailing: IconButton(icon: const Icon(Icons.delete_outline), tooltip: 'Remove', onPressed: () => _remove(v)),
              ),
            );
          },
        ),
      );
}

class _AddVehicleSheet extends StatefulWidget {
  const _AddVehicleSheet();
  @override
  State<_AddVehicleSheet> createState() => _AddVehicleSheetState();
}

class _AddVehicleSheetState extends State<_AddVehicleSheet> {
  final _plate = TextEditingController();
  final _make = TextEditingController();
  final _model = TextEditingController();
  final _colour = TextEditingController();
  late int _unit = Session.instance.me!.residencies.first.unit;
  bool _busy = false;
  String? _error;

  Future<void> _save() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await Api.instance.post('/v1/vehicles/', {
        'unit': _unit, 'plate_number': _plate.text.trim(), 'make': _make.text.trim(), 'model': _model.text.trim(), 'colour': _colour.text.trim(),
      });
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final units = Session.instance.me!.residencies;
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, MediaQuery.viewInsetsOf(context).bottom + 20),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('Add vehicle', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 16),
        if (_error != null) Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error))),
        if (units.length > 1) ...[
          DropdownButtonFormField<int>(
            initialValue: _unit,
            decoration: const InputDecoration(labelText: 'Unit'),
            items: [for (final r in units) DropdownMenuItem(value: r.unit, child: Text(r.unitDisplay))],
            onChanged: (v) => setState(() => _unit = v ?? _unit),
          ),
          const SizedBox(height: 12),
        ],
        TextField(controller: _plate, autofocus: true, textCapitalization: TextCapitalization.characters, decoration: const InputDecoration(labelText: 'Plate number', hintText: 'SBA1234A')),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: TextField(controller: _make, decoration: const InputDecoration(labelText: 'Make'))),
          const SizedBox(width: 12),
          Expanded(child: TextField(controller: _model, decoration: const InputDecoration(labelText: 'Model'))),
        ]),
        const SizedBox(height: 12),
        TextField(controller: _colour, decoration: const InputDecoration(labelText: 'Colour')),
        const SizedBox(height: 20),
        FilledButton(onPressed: _busy ? null : _save, child: const Text('Save')),
      ]),
    );
  }
}


/// Pay for season parking: pick the plate (or renew one), the months, then pay on HitPay.
class _SeasonParkingSheet extends StatefulWidget {
  const _SeasonParkingSheet({required this.offer, this.vehicle});
  final ParkingOffer offer;
  final Vehicle? vehicle;
  @override
  State<_SeasonParkingSheet> createState() => _SeasonParkingSheetState();
}

class _SeasonParkingSheetState extends State<_SeasonParkingSheet> {
  late final _plate = TextEditingController(text: widget.vehicle?.plate ?? '');
  late final _holder = TextEditingController(text: widget.vehicle?.holderName ?? '');
  late int _unit = Session.instance.me!.residencies.first.unit;
  late int _months = widget.offer.months.first;
  bool _busy = false;
  String? _error;

  String get _total => '${widget.offer.currency} ${(widget.offer.monthlyFee * _months).toStringAsFixed(2)}';

  Future<void> _pay() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final data = await Api.instance.post('/v1/parking-permits/', {
        'unit': _unit, 'plate_number': _plate.text.trim(), 'holder_name': _holder.text.trim(), 'months': _months,
      }) as Map<String, dynamic>;
      if (!mounted) return;
      final permit = (data['permit'] as Map).cast<String, dynamic>();
      final result = await payOnline(context,
          resource: 'parking-permits', event: 'parking_permit', id: permit['id'] as int,
          url: data['payment_url'] as String, returnPrefix: data['return_url_prefix'] as String? ?? '');
      if (!mounted) return;
      final paid = result?['status'] == 'paid';
      showMessage(context, paid
          ? 'Paid. ${permit['plate_number']} parks until ${DateFormat('d MMM y').format(DateTime.parse(result!['ends_on'] as String))}.'
          : 'Season parking not paid yet. Try again from Vehicles.');
      Navigator.pop(context, paid);
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final units = Session.instance.me!.residencies;
    final renewing = widget.vehicle != null;
    final lots = widget.offer.lotsLeft;
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, MediaQuery.viewInsetsOf(context).bottom + 20),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(renewing ? 'Renew ${widget.vehicle!.plate}' : 'Season parking', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 4),
        Text(
          '${widget.offer.currency} ${widget.offer.monthlyFee.toStringAsFixed(2)} a month. The barrier opens for the plate once it is paid'
          '${renewing ? ', from the day after the current pass ends' : ''}.',
          style: TextStyle(color: Theme.of(context).colorScheme.outline),
        ),
        if (!renewing && lots != null) ...[
          const SizedBox(height: 4),
          Text('$lots lot${lots == 1 ? '' : 's'} left', style: TextStyle(color: Theme.of(context).colorScheme.outline)),
        ],
        const SizedBox(height: 16),
        if (_error != null) Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error))),
        if (units.length > 1 && !renewing) ...[
          DropdownButtonFormField<int>(
            initialValue: _unit,
            decoration: const InputDecoration(labelText: 'Unit'),
            items: [for (final r in units) DropdownMenuItem(value: r.unit, child: Text(r.unitDisplay))],
            onChanged: (v) => setState(() => _unit = v ?? _unit),
          ),
          const SizedBox(height: 12),
        ],
        if (!renewing) ...[
          TextField(controller: _plate, autofocus: true, textCapitalization: TextCapitalization.characters,
              decoration: const InputDecoration(labelText: 'Plate number', hintText: 'SBA1234A')),
          const SizedBox(height: 12),
          TextField(controller: _holder, decoration: const InputDecoration(labelText: 'Driver name', hintText: 'e.g. your visitor or tenant')),
          const SizedBox(height: 16),
        ],
        Text('How long', style: Theme.of(context).textTheme.labelLarge),
        const SizedBox(height: 8),
        Wrap(spacing: 8, children: [
          for (final m in widget.offer.months)
            ChoiceChip(label: Text('$m month${m == 1 ? '' : 's'}'), selected: _months == m, onSelected: (_) => setState(() => _months = m)),
        ]),
        const SizedBox(height: 20),
        FilledButton(onPressed: _busy ? null : _pay, child: Text(_busy ? 'Opening payment…' : 'Pay $_total')),
      ]),
    );
  }
}
