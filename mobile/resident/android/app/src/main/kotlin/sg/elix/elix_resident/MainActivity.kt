package sg.elix.elix_resident

import android.media.AudioAttributes
import android.media.Ringtone
import android.media.RingtoneManager
import android.os.Build
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var ringtone: Ringtone? = null

    /** "elix/ringer": play / stop the phone's own ringtone while the in-app call screen is showing. */
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "elix/ringer").setMethodCallHandler { call, result ->
            when (call.method) {
                "start" -> { startRinging(); result.success(null) }
                "stop" -> { stopRinging(); result.success(null) }
                else -> result.notImplemented()
            }
        }
    }

    private fun startRinging() {
        stopRinging()
        val uri = RingtoneManager.getActualDefaultRingtoneUri(this, RingtoneManager.TYPE_RINGTONE)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
        ringtone = RingtoneManager.getRingtone(applicationContext, uri)?.apply {
            // Ring stream: follows the phone's ring volume and silent mode.
            audioAttributes = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) isLooping = true
            play()
        }
    }

    private fun stopRinging() {
        ringtone?.stop()
        ringtone = null
    }

    override fun onDestroy() {
        stopRinging()
        super.onDestroy()
    }
}
