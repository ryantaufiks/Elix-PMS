import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:share_plus/share_plus.dart';

import '../api.dart';
import '../realtime.dart';
import '../session.dart';
import 'paged_list.dart';
import 'payment_screen.dart';
import 'widgets.dart';

final _date = DateFormat('d MMM y');

const _categories = {
  'hacking': 'Hacking and tiling',
  'carpentry': 'Carpentry',
  'painting': 'Painting',
  'electrical': 'Electrical',
  'plumbing': 'Plumbing',
  'aircon': 'Air-conditioning',
  'other': 'Other',
};

const _statusColors = {
  'pending_payment': Color(0xFFB45309),
  'submitted': Color(0xFFB45309),
  'approved': Color(0xFF15803D),
  'rejected': Color(0xFFDC2626),
  'cancelled': Color(0xFF64748B),
  'completed': Color(0xFF2563EB),
};

/// e-Permit to Work: apply to renovate, pay the deposit, and share the contractor's pass once approved.
class RenovationScreen extends StatefulWidget {
  const RenovationScreen({super.key});
  @override
  State<RenovationScreen> createState() => _RenovationScreenState();
}

class _RenovationScreenState extends State<RenovationScreen> {
  final _list = GlobalKey<PagedListState<Map<String, dynamic>>>();
  StreamSubscription? _events;

  @override
  void initState() {
    super.initState();
    _events = Realtime.instance.events.listen((event) {
      if (event['type'] == 'permit') _list.currentState?.reload();
    });
  }

  @override
  void dispose() {
    _events?.cancel();
    super.dispose();
  }

  Future<void> _apply() async {
    final done = await Navigator.of(context).push<bool>(
        MaterialPageRoute(fullscreenDialog: true, builder: (_) => const _ApplyScreen()));
    if (done == true) _list.currentState?.reload();
  }

  Future<void> _pay(Map<String, dynamic> p) async {
    try {
      final data = await Api.instance.post('/v1/renovation-permits/${p['id']}/pay/') as Map<String, dynamic>;
      if (!mounted) return;
      final result = await payOnline(context, resource: 'renovation-permits', event: 'permit', id: p['id'] as int,
          url: data['payment_url'] as String, returnPrefix: data['return_url_prefix'] as String? ?? '');
      if (mounted && result?['status'] == 'submitted') showMessage(context, 'Deposit paid. Your permit is with the management office.');
    } catch (e) {
      if (mounted) showError(context, e);
    }
    _list.currentState?.reload();
  }

  Future<void> _cancel(Map<String, dynamic> p) async {
    try {
      await Api.instance.post('/v1/renovation-permits/${p['id']}/cancel/');
    } catch (e) {
      if (mounted) showError(context, e);
    }
    _list.currentState?.reload();
  }

  void _share(Map<String, dynamic> p) {
    SharePlus.instance.share(ShareParams(
      subject: 'Your contractor pass',
      text: 'Contractor pass for ${p['contractor_company']} (${_date.format(DateTime.parse(p['start_date'] as String))} – '
          '${_date.format(DateTime.parse(p['end_date'] as String))}). Show the QR code at the gate kiosk: ${p['pass_url']}',
    ));
  }

  @override
  Widget build(BuildContext context) {
    final outline = Theme.of(context).colorScheme.outline;
    return Scaffold(
      appBar: AppBar(title: const Text('Renovation')),
      floatingActionButton: FloatingActionButton.extended(onPressed: _apply, icon: const Icon(Icons.add), label: const Text('Apply')),
      body: PagedList<Map<String, dynamic>>(
        key: _list,
        path: '/v1/renovation-permits/',
        parse: (json) => json,
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
        empty: const EmptyState(icon: Icons.construction_rounded,
            text: 'Apply for a renovation permit before your contractor starts. Once approved, share their pass.'),
        itemBuilder: (context, p) {
          final status = p['status'] as String;
          return Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Expanded(child: Text(p['contractor_company'] as String, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16))),
                  StatusChip(p['status_display'] as String, color: _statusColors[status] ?? outline),
                ]),
                const SizedBox(height: 4),
                Text('${p['category_display']} · ${_date.format(DateTime.parse(p['start_date'] as String))} – '
                    '${_date.format(DateTime.parse(p['end_date'] as String))}', style: TextStyle(color: outline)),
                if ((p['decision_note'] as String? ?? '').isNotEmpty)
                  Padding(padding: const EdgeInsets.only(top: 6), child: Text('Office: ${p['decision_note']}')),
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Wrap(alignment: WrapAlignment.end, spacing: 8, runSpacing: 4, children: [
                    if (status == 'pending_payment' || status == 'submitted')
                      TextButton(onPressed: () => _cancel(p), child: const Text('Cancel')),
                    if (status == 'pending_payment')
                      FilledButton(onPressed: () => _pay(p), child: Text('Pay deposit ${p['currency']} ${p['deposit']}')),
                    if (status == 'approved' && (p['pass_url'] as String? ?? '').isNotEmpty)
                      FilledButton.icon(onPressed: () => _share(p), icon: const Icon(Icons.share), label: const Text('Share contractor pass')),
                  ]),
                ),
              ]),
            ),
          );
        },
      ),
    );
  }
}

class _ApplyScreen extends StatefulWidget {
  const _ApplyScreen();
  @override
  State<_ApplyScreen> createState() => _ApplyScreenState();
}

class _ApplyScreenState extends State<_ApplyScreen> {
  final _units = Session.instance.me!.residencies.where((r) => r.renovationPermits).toList();
  late int _unit = _units.first.unit;
  String _category = 'carpentry';
  final _description = TextEditingController();
  final _company = TextEditingController();
  final _contact = TextEditingController();
  final _phone = TextEditingController();
  final _plates = TextEditingController();
  int _workers = 2;
  DateTime _start = DateTime.now().add(const Duration(days: 3));
  DateTime _end = DateTime.now().add(const Duration(days: 10));
  bool _agreed = false;
  bool _busy = false;
  String? _error;

  String get _terms => _units.firstWhere((r) => r.unit == _unit).renovationTerms;

  Future<void> _pick(bool start) async {
    final current = start ? _start : _end;
    final picked = await showDatePicker(context: context, initialDate: current,
        firstDate: start ? DateTime.now() : _start, lastDate: DateTime.now().add(const Duration(days: 365)));
    if (picked == null) return;
    setState(() {
      if (start) {
        _start = picked;
        if (_end.isBefore(_start)) _end = _start;
      } else {
        _end = picked;
      }
    });
  }

  Future<void> _submit() async {
    if (_company.text.trim().isEmpty) return setState(() => _error = 'Enter the contractor company.');
    if (_terms.isNotEmpty && !_agreed) return setState(() => _error = 'Please agree to the renovation rules.');
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final iso = DateFormat('yyyy-MM-dd');
      final data = await Api.instance.post('/v1/renovation-permits/', {
        'unit': _unit, 'category': _category, 'description': _description.text.trim(),
        'contractor_company': _company.text.trim(), 'contractor_contact': _contact.text.trim(), 'contractor_phone': _phone.text.trim(),
        'workers': _workers, 'start_date': iso.format(_start), 'end_date': iso.format(_end),
        'plates': _plates.text.split(RegExp(r'[,\s]+')).where((p) => p.isNotEmpty).toList(),
      }) as Map<String, dynamic>;
      if (!mounted) return;
      final permit = (data['permit'] as Map).cast<String, dynamic>();
      final url = data['payment_url'] as String? ?? '';
      if (url.isNotEmpty) {
        final result = await payOnline(context, resource: 'renovation-permits', event: 'permit', id: permit['id'] as int,
            url: url, returnPrefix: data['return_url_prefix'] as String? ?? '');
        if (!mounted) return;
        showMessage(context, result?['status'] == 'submitted'
            ? 'Deposit paid. Your permit is with the management office.'
            : 'Deposit not paid yet. Pay it from Renovation before it expires.');
      } else {
        showMessage(context, 'Sent to the management office. You will be told when it is approved.');
      }
      Navigator.pop(context, true);
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final outline = Theme.of(context).colorScheme.outline;
    return Scaffold(
      appBar: AppBar(title: const Text('Apply for renovation')),
      body: ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 32), children: [
        if (_error != null)
          Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error))),
        if (_units.length > 1) ...[
          DropdownButtonFormField<int>(
            initialValue: _unit,
            decoration: const InputDecoration(labelText: 'Unit'),
            items: [for (final r in _units) DropdownMenuItem(value: r.unit, child: Text(r.unitDisplay))],
            onChanged: (v) => setState(() => _unit = v ?? _unit),
          ),
          const SizedBox(height: 12),
        ],
        DropdownButtonFormField<String>(
          initialValue: _category,
          decoration: const InputDecoration(labelText: 'Type of work'),
          items: [for (final e in _categories.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
          onChanged: (v) => setState(() => _category = v ?? _category),
        ),
        const SizedBox(height: 12),
        TextField(controller: _description, maxLines: 2, decoration: const InputDecoration(labelText: 'What will be done', hintText: 'e.g. Replace kitchen cabinets')),
        const SizedBox(height: 20),
        Text('Contractor', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        TextField(controller: _company, decoration: const InputDecoration(labelText: 'Company')),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: TextField(controller: _contact, decoration: const InputDecoration(labelText: 'Contact person'))),
          const SizedBox(width: 12),
          Expanded(child: TextField(controller: _phone, keyboardType: TextInputType.phone, decoration: const InputDecoration(labelText: 'Mobile'))),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          const Expanded(child: Text('Workers on site at once')),
          IconButton(tooltip: 'Fewer', onPressed: _workers > 1 ? () => setState(() => _workers--) : null, icon: const Icon(Icons.remove_circle_outline)),
          Text('$_workers', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
          IconButton(tooltip: 'More', onPressed: _workers < 50 ? () => setState(() => _workers++) : null, icon: const Icon(Icons.add_circle_outline)),
        ]),
        TextField(controller: _plates, textCapitalization: TextCapitalization.characters,
            decoration: const InputDecoration(labelText: 'Vehicle plates (optional)', hintText: 'GBA1234A', helperText: 'Up to 3: the barrier opens for them during the works.')),
        const SizedBox(height: 20),
        Text('Dates', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: OutlinedButton(onPressed: () => _pick(true), child: Text('From ${_date.format(_start)}'))),
          const SizedBox(width: 12),
          Expanded(child: OutlinedButton(onPressed: () => _pick(false), child: Text('To ${_date.format(_end)}'))),
        ]),
        const SizedBox(height: 4),
        Text('Your contractor may come on the estate\'s contractor days and hours within these dates.', style: TextStyle(color: outline, fontSize: 13)),
        if (_terms.isNotEmpty) ...[
          const SizedBox(height: 20),
          Text('Renovation rules', style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 6),
          Text(_terms),
          CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            value: _agreed,
            onChanged: (v) => setState(() => _agreed = v ?? false),
            title: const Text('I and my contractor will follow these rules'),
            controlAffinity: ListTileControlAffinity.leading,
          ),
        ],
        const SizedBox(height: 20),
        FilledButton(onPressed: _busy ? null : _submit, child: Text(_busy ? 'Sending…' : 'Submit to the management office')),
        const SizedBox(height: 8),
        Text('If the estate asks for a refundable deposit, you pay it next. Insurance and drawings: send them to the management office.',
            style: TextStyle(color: outline, fontSize: 13)),
      ]),
    );
  }
}
