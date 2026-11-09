import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';

import '../api.dart';
import '../models.dart';
import 'paged_list.dart';
import 'widgets.dart';

const _kinds = <String, (String, IconData)>{
  'ownership': ('Proof of ownership', Icons.home_work_outlined),
  'tenancy': ('Tenancy agreement', Icons.assignment_outlined),
  'identity': ('Identity document', Icons.badge_outlined),
  'other': ('Document', Icons.description_outlined),
};

String _size(int bytes) => bytes < 1024 * 1024 ? '${(bytes / 1024).ceil()} KB' : '${(bytes / 1024 / 1024).toStringAsFixed(1)} MB';

/// The resident's documents kept by the management (ownership, tenancy agreement…), read-only.
class DocumentsScreen extends StatelessWidget {
  const DocumentsScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Documents')),
        body: PagedList<ResidentDocument>(
          path: '/v1/resident-documents/',
          parse: ResidentDocument.new,
          empty: const EmptyState(icon: Icons.folder_open_outlined, text: 'Documents the management keeps for you (proof of ownership, tenancy agreement) appear here.'),
          itemBuilder: (context, d) => _DocumentCard(d),
        ),
      );
}

class _DocumentCard extends StatefulWidget {
  const _DocumentCard(this.document);
  final ResidentDocument document;
  @override
  State<_DocumentCard> createState() => _DocumentCardState();
}

class _DocumentCardState extends State<_DocumentCard> {
  bool _opening = false;

  Future<void> _open() async {
    final d = widget.document;
    setState(() => _opening = true);
    try {
      final bytes = await Api.instance.bytes('/v1/resident-documents/${d.id}/download/');
      if (!mounted) return;
      if (d.isImage) {
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => _ImageViewer(title: d.title, bytes: bytes)));
        return;
      }
      // PDFs open in the phone's viewer. The copy lives in the app's cache, not in shared storage.
      final dir = await Directory.systemTemp.createTemp('doc');
      final file = await File('${dir.path}/${d.fileName.replaceAll(RegExp(r'[\\/]'), '_')}').writeAsBytes(bytes);
      final result = await OpenFilex.open(file.path, type: 'application/pdf');
      if (result.type != ResultType.done && mounted) {
        showError(context, 'No app on this phone can open PDF files.');
      }
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _opening = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = widget.document;
    final (label, icon) = _kinds[d.kind] ?? _kinds['other']!;
    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        leading: CircleAvatar(backgroundColor: scheme.primary.withValues(alpha: 0.12), child: Icon(icon, color: scheme.primary)),
        title: Text(d.title, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text('$label · ${d.unitDisplay}\n${_size(d.size)} · ${formatDateTime(d.createdAt)}'),
        isThreeLine: true,
        trailing: _opening
            ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5))
            : Icon(Icons.open_in_new_rounded, color: scheme.outline),
        onTap: _opening ? null : _open,
      ),
    );
  }
}

class _ImageViewer extends StatelessWidget {
  const _ImageViewer({required this.title, required this.bytes});
  final String title;
  final Uint8List bytes;

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: Colors.black,
        appBar: AppBar(title: Text(title), backgroundColor: Colors.black, foregroundColor: Colors.white),
        body: InteractiveViewer(maxScale: 5, child: Center(child: Image.memory(bytes))),
      );
}
