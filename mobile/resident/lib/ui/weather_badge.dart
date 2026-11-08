import 'package:flutter/material.dart';

import '../api.dart';
import '../models.dart';

/// Temperature and outlook at the condo, for the home header. Hidden while NEA's data is unavailable.
class WeatherBadge extends StatefulWidget {
  const WeatherBadge({super.key, required this.condominium});
  final int condominium;
  @override
  State<WeatherBadge> createState() => WeatherBadgeState();
}

class WeatherBadgeState extends State<WeatherBadge> {
  Weather? _now;
  DateTime? _at;

  @override
  void initState() {
    super.initState();
    refresh();
  }

  /// Fetch again unless the reading is fresh (the server updates it every 5 minutes).
  Future<void> refresh() async {
    if (_at != null && DateTime.now().difference(_at!) < const Duration(minutes: 5)) return;
    try {
      final data = await Api.instance.get('/v1/weather/?condominium=${widget.condominium}') as Map<String, dynamic>;
      if (!mounted) return;
      setState(() {
        _now = Weather(data);
        _at = DateTime.now();
      });
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final now = _now;
    if (now == null || now.temperature == null) return const SizedBox.shrink();
    return Semantics(
      label: '${now.temperature!.round()} degrees, ${now.forecast}',
      child: Column(crossAxisAlignment: CrossAxisAlignment.end, mainAxisSize: MainAxisSize.min, children: [
        Row(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.center, children: [
          Icon(weatherIcon(now.forecast), color: const Color(0xFF93C5FD), size: 34),
          const SizedBox(width: 8),
          Text('${now.temperature!.round()}°', style: const TextStyle(color: Colors.white, fontSize: 40, fontWeight: FontWeight.w300, height: 1)),
        ]),
        const SizedBox(height: 4),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 140),
          child: Text(now.forecast, maxLines: 1, overflow: TextOverflow.ellipsis, textAlign: TextAlign.end,
              style: const TextStyle(color: Color(0xFFCBD5E1), fontSize: 13)),
        ),
      ]),
    );
  }
}

/// Icon for an NEA 2-hour outlook ("Thundery Showers", "Partly Cloudy (Night)"…).
IconData weatherIcon(String forecast) {
  final f = forecast.toLowerCase();
  if (f.contains('thunder')) return Icons.thunderstorm_rounded;
  if (f.contains('rain') || f.contains('shower')) return Icons.water_drop_rounded;
  if (['cloud', 'haz', 'mist', 'fog', 'wind'].any(f.contains)) return Icons.cloud_rounded;
  return f.contains('night') ? Icons.nightlight_round : Icons.wb_sunny_rounded;
}
