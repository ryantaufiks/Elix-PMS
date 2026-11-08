import 'package:flutter/material.dart';

import '../models.dart';
import 'home_tab.dart';
import 'paged_list.dart';
import 'widgets.dart';

/// Every access to the resident's units, newest first, page by page.
class ActivityScreen extends StatelessWidget {
  const ActivityScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Activity')),
        body: PagedList<AccessEntry>(
          path: '/v1/access-logs/',
          parse: AccessEntry.new,
          itemBuilder: (context, entry) => ActivityTile(entry),
          empty: const EmptyState(icon: Icons.history, text: 'Entries for your unit appear here.'),
        ),
      );
}
