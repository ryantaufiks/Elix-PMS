import 'package:flutter/material.dart';

import '../appearance.dart';
import '../config.dart';
import '../push.dart';
import '../session.dart';
import 'documents_screen.dart';
import 'widgets.dart';

class ProfileTab extends StatelessWidget {
  const ProfileTab({super.key});

  @override
  Widget build(BuildContext context) {
    final me = Session.instance.me!;
    final outline = Theme.of(context).colorScheme.outline;
    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Card(
          child: ListTile(
            contentPadding: const EdgeInsets.all(16),
            leading: CircleAvatar(radius: 26, child: Text(me.displayName.characters.first.toUpperCase(), style: const TextStyle(fontSize: 20))),
            title: Text(me.displayName, style: const TextStyle(fontWeight: FontWeight.w600)),
            subtitle: Text(me.username),
          ),
        ),
        const SizedBox(height: 16),
        Text('Your units', style: TextStyle(color: outline)),
        const SizedBox(height: 8),
        for (final r in me.residencies)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Card(
              child: ListTile(
                leading: const Icon(Icons.apartment),
                title: Text(r.unitDisplay),
                subtitle: Text(r.receivesCalls ? 'Receives visitor calls' : 'Visitor calls off (ask management)'),
              ),
            ),
          ),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.folder_outlined),
            title: const Text('Documents'),
            subtitle: const Text('Proof of ownership, tenancy agreement'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const DocumentsScreen())),
          ),
        ),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: Icon(Push.instance.available ? Icons.notifications_active_outlined : Icons.notifications_off_outlined),
            title: Text(Push.instance.available ? 'Calls ring even when the app is closed' : 'Calls ring only while the app is open'),
            subtitle: Push.instance.available ? null : const Text('Push notifications are not set up for this app build.'),
          ),
        ),
        const SizedBox(height: 16),
        Text('Theme', style: TextStyle(color: outline)),
        const SizedBox(height: 8),
        ListenableBuilder(
          listenable: Appearance.instance,
          builder: (context, _) => SegmentedButton<ThemeMode>(
            showSelectedIcon: false,
            segments: const [
              ButtonSegment(value: ThemeMode.system, icon: Icon(Icons.brightness_auto_outlined), label: Text('Auto')),
              ButtonSegment(value: ThemeMode.light, icon: Icon(Icons.light_mode_outlined), label: Text('Light')),
              ButtonSegment(value: ThemeMode.dark, icon: Icon(Icons.dark_mode_outlined), label: Text('Dark')),
            ],
            selected: {Appearance.instance.mode},
            onSelectionChanged: (s) => Appearance.instance.set(s.first),
          ),
        ),
        const SizedBox(height: 24),
        OutlinedButton.icon(
          style: OutlinedButton.styleFrom(minimumSize: const Size(64, 52)),
          onPressed: () => Session.instance.logout(),
          icon: const Icon(Icons.logout),
          label: const Text('Sign out'),
        ),
        const SizedBox(height: 16),
        Center(child: Text('Elix $appVersion · $apiBase', style: TextStyle(color: outline, fontSize: 12))),
        const SizedBox(height: 12),
        const Credit(),
      ]),
    );
  }
}
