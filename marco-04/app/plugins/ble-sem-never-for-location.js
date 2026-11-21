/**
 * A react-native-ble-manager declara BLUETOOTH_SCAN com
 * usesPermissionFlags="neverForLocation". Com essa marca o Android pode
 * esconder anúncios com cara de farol (beacon) — justamente o que a âncora
 * é. Este plugin manda o merge do manifesto remover a marca; em troca, o app
 * pede também a permissão de localização (ver src/lib/ble.ts).
 */
const { withAndroidManifest, AndroidConfig } = require('expo/config-plugins');

module.exports = function semNeverForLocation(config) {
  return withAndroidManifest(config, (cfg) => {
    const m = cfg.modResults;
    AndroidConfig.Manifest.ensureToolsAvailable(m);
    m.manifest['uses-permission'] = m.manifest['uses-permission'] || [];
    let scan = m.manifest['uses-permission'].find(
      (p) => p.$['android:name'] === 'android.permission.BLUETOOTH_SCAN');
    if (!scan) {
      scan = { $: { 'android:name': 'android.permission.BLUETOOTH_SCAN', 'tools:targetApi': '31' } };
      m.manifest['uses-permission'].push(scan);
    }
    delete scan.$['android:usesPermissionFlags'];
    scan.$['tools:remove'] = 'android:usesPermissionFlags';
    return cfg;
  });
};
