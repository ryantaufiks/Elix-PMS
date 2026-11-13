import 'package:flutter/material.dart';

// Dark enough for white text (5.2:1); dark mode uses brandBlueLight with navy text instead (WCAG AA).
const brandBlue = Color(0xFF2563EB);
const brandBlueLight = Color(0xFF8FB8FF);
const navy = Color(0xFF0B1631);
const navyDeep = Color(0xFF070F24);

ThemeData buildTheme(Brightness brightness) {
  final dark = brightness == Brightness.dark;
  final scheme = ColorScheme.fromSeed(seedColor: brandBlue, brightness: brightness,
      primary: dark ? brandBlueLight : brandBlue, onPrimary: dark ? navyDeep : Colors.white,
      surface: dark ? const Color(0xFF0F1A2E) : Colors.white);
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: dark ? const Color(0xFF0A1222) : const Color(0xFFF3F5F9),
    appBarTheme: AppBarTheme(
      backgroundColor: dark ? const Color(0xFF0A1222) : const Color(0xFFF3F5F9),
      surfaceTintColor: Colors.transparent,
      centerTitle: false,
      titleTextStyle: TextStyle(fontSize: 22, fontWeight: FontWeight.w600, color: scheme.onSurface),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      margin: EdgeInsets.zero,
      color: scheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: dark ? const Color(0xFF20304F) : const Color(0xFFE4E8F0)),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: dark ? const Color(0xFF13203A) : Colors.white,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: dark ? const Color(0xFF20304F) : const Color(0xFFE4E8F0)),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(minimumSize: const Size(64, 52), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: scheme.surface,
      indicatorColor: brandBlue.withValues(alpha: 0.15),
      surfaceTintColor: Colors.transparent,
    ),
  );
}
