import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../api.dart';
import '../models.dart';
import '../session.dart';
import 'paged_list.dart';
import 'widgets.dart';

class VehiclesTab extends StatefulWidget {
  const VehiclesTab({super.key});
  @override
  State<VehiclesTab> createState() => _VehiclesTabState();
}

class _VehiclesTabState extends State<VehiclesTab> {
  final _list = GlobalKey<PagedListState<Vehicle>>();

  void _load() => _list.currentState?.reload();

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
        appBar: AppBar(title: const Text('Vehicles')),
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
