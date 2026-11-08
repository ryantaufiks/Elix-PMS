import 'package:flutter/material.dart';

import '../api.dart';
import '../models.dart';
import '../session.dart';
import 'widgets.dart';

/// Open the condominium's gates remotely (only gates the management allows). Every opening is logged.
class AccessScreen extends StatefulWidget {
  const AccessScreen({super.key});
  @override
  State<AccessScreen> createState() => _AccessScreenState();
}

class _AccessScreenState extends State<AccessScreen> {
  List<Gate>? _gates;
  int? _selected;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final condos = Session.instance.me!.residencies.map((r) => r.condominium).toSet();
      final gates = <Gate>[];
      for (final condo in condos) {
        final rows = await Api.instance.list('/v1/gates/?condominium=$condo&resident_remote_open=true&is_active=true&page_size=50');
        gates.addAll(rows.map(Gate.new));
      }
      if (!mounted) return;
      setState(() {
        _gates = gates;
        _selected ??= gates.isEmpty ? null : gates.first.id;
      });
    } catch (e) {
      if (mounted) {
        setState(() => _gates = []);
        showError(context, e);
      }
    }
  }

  Future<void> _open() async {
    final gate = _gates!.firstWhere((g) => g.id == _selected);
    try {
      await Api.instance.post('/v1/gates/${gate.id}/remote_open/');
      if (mounted) showMessage(context, '${gate.name} is opening.');
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  IconData _icon(Gate g) => switch (g.type) {
        'pedestrian' => Icons.directions_walk,
        'door' => Icons.door_front_door_outlined,
        _ => Icons.directions_car_outlined,
      };

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Access')),
      body: _gates == null
          ? const Center(child: CircularProgressIndicator())
          : _gates!.isEmpty
              ? RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(children: const [
                    EmptyState(icon: Icons.lock_outline, text: 'No gates can be opened from the app yet.\nAsk your management office to enable remote access.'),
                  ]),
                )
              : ListView(padding: const EdgeInsets.all(16), children: [
                  Text('Choose a gate', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 12),
                  for (final g in _gates!)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Card(
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(16),
                          side: BorderSide(color: g.id == _selected ? scheme.primary : scheme.outlineVariant, width: g.id == _selected ? 2 : 1),
                        ),
                        child: ListTile(
                          leading: CircleAvatar(backgroundColor: scheme.primary.withValues(alpha: 0.12), child: Icon(_icon(g), color: scheme.primary)),
                          title: Text(g.name, style: const TextStyle(fontWeight: FontWeight.w600)),
                          trailing: g.id == _selected ? Icon(Icons.check_circle, color: scheme.primary) : null,
                          onTap: () => setState(() => _selected = g.id),
                        ),
                      ),
                    ),
                  const SizedBox(height: 24),
                  if (_selected != null) SwipeToUnlock(onUnlock: _open),
                  const SizedBox(height: 16),
                  Text('Openings are recorded with your name and unit.', textAlign: TextAlign.center,
                      style: TextStyle(color: scheme.outline, fontSize: 13)),
                ]),
    );
  }
}
