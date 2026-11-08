import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';

import '../api.dart';
import '../models.dart';
import '../session.dart';
import 'paged_list.dart';
import 'widgets.dart';

class InvitationsTab extends StatefulWidget {
  const InvitationsTab({super.key});
  @override
  State<InvitationsTab> createState() => _InvitationsTabState();
}

class _InvitationsTabState extends State<InvitationsTab> {
  final _list = GlobalKey<PagedListState<Invitation>>();
  bool _showPast = false;

  Future<void> _load() async => _list.currentState?.reload();

  Future<void> _create() async {
    final created = await Navigator.of(context).push<Invitation>(MaterialPageRoute(builder: (_) => const CreateInvitationScreen(), fullscreenDialog: true));
    if (created != null) {
      await _load();
      if (mounted) Navigator.of(context).push(MaterialPageRoute(builder: (_) => InvitationDetailScreen(invitation: created)));
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Invitations'), actions: [
          TextButton(onPressed: () => setState(() => _showPast = !_showPast), child: Text(_showPast ? 'Active only' : 'Show all')),
        ]),
        floatingActionButton: FloatingActionButton.extended(onPressed: _create, icon: const Icon(Icons.add), label: const Text('Invite visitor')),
        body: PagedList<Invitation>(
          key: _list,
          path: '/v1/invitations/?ordering=-valid_from${_showPast ? '' : '&status=active'}',
          parse: Invitation.new,
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
          empty: const EmptyState(icon: Icons.confirmation_number_outlined, text: 'No invitations yet.\nInvite a visitor and share the QR code with them.'),
          itemBuilder: (context, inv) {
            return Card(
              child: ListTile(
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                title: Text(inv.visitorName, style: const TextStyle(fontWeight: FontWeight.w600)),
                subtitle: Text('${purposeLabel[inv.purpose]} · ${formatDateTime(inv.validFrom)} → ${formatDateTime(inv.validUntil)}'),
                trailing: _statusChip(inv.status),
                onTap: () async {
                  await Navigator.of(context).push(MaterialPageRoute(builder: (_) => InvitationDetailScreen(invitation: inv)));
                  _load();
                },
              ),
            );
          },
        ),
      );
}

Widget _statusChip(String status) => switch (status) {
      'active' => const StatusChip('Active', color: Color(0xFF16A34A)),
      'completed' => const StatusChip('Used', color: Color(0xFF2F6FFF)),
      'expired' => const StatusChip('Expired', color: Color(0xFFD97706)),
      _ => const StatusChip('Cancelled', color: Color(0xFF64748B)),
    };

class InvitationDetailScreen extends StatefulWidget {
  const InvitationDetailScreen({super.key, required this.invitation});
  final Invitation invitation;
  @override
  State<InvitationDetailScreen> createState() => _InvitationDetailScreenState();
}

class _InvitationDetailScreenState extends State<InvitationDetailScreen> {
  late Invitation _inv = widget.invitation;

  void _share() {
    SharePlus.instance.share(ShareParams(
      subject: 'Your visitor pass',
      text: 'Hi ${_inv.visitorName}, here is your visitor pass for ${formatDateTime(_inv.validFrom)}. '
          'Show the QR code at the gate kiosk: ${_inv.shareUrl}',
    ));
  }

  Future<void> _cancel() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Cancel invitation?'),
        content: Text('The QR code for ${_inv.visitorName} stops working immediately.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Cancel invitation')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      final data = await Api.instance.post('/v1/invitations/${_inv.id}/cancel/');
      setState(() => _inv = Invitation(data as Map<String, dynamic>));
      if (mounted) showMessage(context, 'Invitation cancelled.');
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final active = _inv.status == 'active';
    return Scaffold(
      appBar: AppBar(title: Text(_inv.visitorName)),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(children: [
              Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                Text(purposeLabel[_inv.purpose] ?? '', style: Theme.of(context).textTheme.titleMedium),
                _statusChip(_inv.status),
              ]),
              const SizedBox(height: 16),
              if (active)
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(12)),
                  child: SizedBox(width: 220, height: 220, child: AuthImage('/v1/invitations/${_inv.id}/qr/', fit: BoxFit.contain)),
                )
              else
                const Padding(padding: EdgeInsets.all(24), child: Icon(Icons.qr_code_2, size: 80, color: Colors.grey)),
              const SizedBox(height: 16),
              _row(context, 'Unit', _inv.unitDisplay),
              _row(context, 'Valid from', formatDateTime(_inv.validFrom)),
              _row(context, 'Valid until', formatDateTime(_inv.validUntil)),
              _row(context, 'Entries', _inv.maxEntries == 0 ? '${_inv.entryCount} (unlimited)' : '${_inv.entryCount} of ${_inv.maxEntries}'),
              if (_inv.plate.isNotEmpty) _row(context, 'Vehicle', _inv.plate),
              if (_inv.visitorPhone.isNotEmpty) _row(context, 'Mobile', _inv.visitorPhone),
            ]),
          ),
        ),
        const SizedBox(height: 16),
        if (active) ...[
          FilledButton.icon(onPressed: _share, icon: const Icon(Icons.share), label: const Text('Share with visitor')),
          const SizedBox(height: 8),
          OutlinedButton(onPressed: _cancel, style: OutlinedButton.styleFrom(minimumSize: const Size(64, 52)), child: const Text('Cancel invitation')),
        ],
      ]),
    );
  }

  Widget _row(BuildContext context, String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(children: [
          Expanded(child: Text(k, style: TextStyle(color: Theme.of(context).colorScheme.outline))),
          Flexible(child: Text(v, textAlign: TextAlign.right, style: const TextStyle(fontWeight: FontWeight.w500))),
        ]),
      );
}

class CreateInvitationScreen extends StatefulWidget {
  const CreateInvitationScreen({super.key});
  @override
  State<CreateInvitationScreen> createState() => _CreateInvitationScreenState();
}

class _CreateInvitationScreenState extends State<CreateInvitationScreen> {
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _plate = TextEditingController();
  final _notes = TextEditingController();
  late int _unit = Session.instance.me!.residencies.first.unit;
  String _purpose = 'guest';
  DateTime _from = DateTime.now();
  DateTime _until = DateTime.now().add(const Duration(hours: 4));
  int _entries = 1;
  bool _busy = false;
  Map<String, String> _errors = {};

  Future<void> _pick(bool start) async {
    final current = start ? _from : _until;
    final date = await showDatePicker(context: context, initialDate: current, firstDate: DateTime.now().subtract(const Duration(days: 1)), lastDate: DateTime.now().add(const Duration(days: 365)));
    if (date == null || !mounted) return;
    final time = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(current));
    if (time == null) return;
    final value = DateTime(date.year, date.month, date.day, time.hour, time.minute);
    setState(() {
      if (start) {
        _from = value;
        if (!_until.isAfter(_from)) _until = _from.add(const Duration(hours: 4));
      } else {
        _until = value;
      }
    });
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty) {
      setState(() => _errors = {'visitor_name': 'Enter the visitor\'s name.'});
      return;
    }
    setState(() {
      _busy = true;
      _errors = {};
    });
    try {
      final data = await Api.instance.post('/v1/invitations/', {
        'unit': _unit,
        'visitor_name': _name.text.trim(),
        'visitor_phone': _phone.text.trim(),
        'purpose': _purpose,
        'valid_from': _from.toUtc().toIso8601String(),
        'valid_until': _until.toUtc().toIso8601String(),
        'max_entries': _entries,
        'vehicle_plate': _plate.text.trim(),
        'notes': _notes.text.trim(),
      });
      if (mounted) Navigator.pop(context, Invitation(data as Map<String, dynamic>));
    } on ApiException catch (e) {
      final data = e.data;
      setState(() => _errors = data is Map ? {for (final entry in data.entries) '${entry.key}': errorMessage(entry.value, 'Invalid')} : {'detail': e.message});
      if (data is! Map && mounted) showError(context, e);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final units = Session.instance.me!.residencies;
    return Scaffold(
      appBar: AppBar(title: const Text('Invite a visitor')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        if (_errors['detail'] != null || _errors['non_field_errors'] != null)
          Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(_errors['detail'] ?? _errors['non_field_errors']!, style: TextStyle(color: Theme.of(context).colorScheme.error))),
        if (units.length > 1) ...[
          DropdownButtonFormField<int>(
            initialValue: _unit,
            decoration: const InputDecoration(labelText: 'Unit'),
            items: [for (final r in units) DropdownMenuItem(value: r.unit, child: Text(r.unitDisplay))],
            onChanged: (v) => setState(() => _unit = v ?? _unit),
          ),
          const SizedBox(height: 12),
        ],
        TextField(controller: _name, textCapitalization: TextCapitalization.words, decoration: InputDecoration(labelText: 'Visitor name', errorText: _errors['visitor_name'])),
        const SizedBox(height: 12),
        TextField(controller: _phone, keyboardType: TextInputType.phone, decoration: InputDecoration(labelText: 'Mobile (optional)', hintText: '+65 9123 4567', errorText: _errors['visitor_phone'])),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: _purpose,
          decoration: const InputDecoration(labelText: 'Purpose'),
          items: [for (final e in purposeLabel.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
          onChanged: (v) => setState(() => _purpose = v ?? _purpose),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: _DateField(label: 'From', value: _from, onTap: () => _pick(true))),
          const SizedBox(width: 12),
          Expanded(child: _DateField(label: 'Until', value: _until, onTap: () => _pick(false), error: _errors['valid_until'])),
        ]),
        const SizedBox(height: 12),
        TextField(controller: _plate, textCapitalization: TextCapitalization.characters,
            decoration: InputDecoration(labelText: 'Vehicle plate (optional)', hintText: 'SBA1234A', helperText: 'The barrier opens automatically for this plate.', errorText: _errors['vehicle_plate'])),
        const SizedBox(height: 12),
        Row(children: [
          const Expanded(child: Text('Entries allowed')),
          SegmentedButton<int>(
            segments: const [ButtonSegment(value: 1, label: Text('1')), ButtonSegment(value: 2, label: Text('2')), ButtonSegment(value: 5, label: Text('5')), ButtonSegment(value: 0, label: Text('Any'))],
            selected: {_entries},
            onSelectionChanged: (s) => setState(() => _entries = s.first),
          ),
        ]),
        const SizedBox(height: 12),
        TextField(controller: _notes, decoration: const InputDecoration(labelText: 'Note for the guardhouse (optional)')),
        const SizedBox(height: 24),
        FilledButton(
          onPressed: _busy ? null : _submit,
          child: _busy ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5)) : const Text('Create invitation'),
        ),
      ]),
    );
  }
}

class _DateField extends StatelessWidget {
  const _DateField({required this.label, required this.value, required this.onTap, this.error});
  final String label;
  final DateTime value;
  final VoidCallback onTap;
  final String? error;
  @override
  Widget build(BuildContext context) => InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: InputDecorator(
          decoration: InputDecoration(labelText: label, errorText: error, errorMaxLines: 3),
          child: Text(formatDateTime(value)),
        ),
      );
}
