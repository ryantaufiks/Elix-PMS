/// Server address. Override at build time: --dart-define=API_BASE=https://example.com
const apiBase = String.fromEnvironment('API_BASE', defaultValue: 'https://elixsmart.cloud');
const appVersion = '1.0.0';
