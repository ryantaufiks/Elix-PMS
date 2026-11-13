"use client";

// Kiosk languages: the four official languages of Singapore. Strings are keyed by their English text, so a
// missing entry (or a message from the server) simply shows in English. Placeholders look like {name}.
import { createContext, useCallback, useContext } from "react";

export type Lang = "en" | "zh" | "ms" | "ta";

export const LANGS: { code: Lang; label: string; short: string; locale: string; name: string }[] = [
  { code: "en", label: "English", short: "EN", locale: "en-SG", name: "English" },
  { code: "zh", label: "中文", short: "中文", locale: "zh-SG", name: "Mandarin Chinese" },
  { code: "ms", label: "Melayu", short: "BM", locale: "ms-SG", name: "Malay" },
  { code: "ta", label: "தமிழ்", short: "தமிழ்", locale: "ta-SG", name: "Tamil" },
];

type Vars = Record<string, string | number>;
export type Translate = (text: string, vars?: Vars) => string;

// [中文, Melayu, தமிழ்]
const STRINGS: Record<string, [string, string, string]> = {
  // Frame, journeys and the welcome screen
  "← Back": ["← 返回", "← Kembali", "← பின்செல்"],
  "Language": ["语言", "Bahasa", "மொழி"],
  "Call a resident": ["呼叫住户", "Hubungi penghuni", "குடியிருப்பாளரை அழைக்கவும்"],
  "Walk in": ["现场登记", "Daftar masuk", "நேரடிப் பதிவு"],
  "Scan QR code": ["扫描二维码", "Imbas kod QR", "QR குறியீட்டை ஸ்கேன் செய்யவும்"],
  "Check out": ["离开登记", "Daftar keluar", "வெளியேறுதல்"],
  "Call the guardhouse": ["呼叫保安亭", "Hubungi pondok pengawal", "காவலர் அறையை அழைக்கவும்"],
  "Step {step} of {of}": ["第 {step} 步，共 {of} 步", "Langkah {step} daripada {of}", "படி {step} / {of}"],
  "Welcome": ["欢迎", "Selamat datang", "நல்வரவு"],
  "How would you like to enter?": ["您想如何进入？", "Bagaimana anda mahu masuk?", "எப்படி உள்ளே செல்ல விரும்புகிறீர்கள்?"],
  "How would you like to enter through {gate}?": ["您想如何从{gate}进入？", "Bagaimana anda mahu masuk melalui {gate}?", "{gate} வழியாக எப்படி உள்ளே செல்ல விரும்புகிறீர்கள்?"],
  "Video call the unit you are visiting.": ["与您要拜访的单位进行视频通话。", "Buat panggilan video ke unit yang anda lawati.", "நீங்கள் செல்லும் வீட்டை வீடியோ அழைப்பில் தொடர்பு கொள்ளுங்கள்."],
  "Register your visit and get a pass slip for security.": ["登记您的来访，并领取通行单出示给保安。", "Daftar lawatan anda dan dapatkan slip pas untuk pengawal keselamatan.", "உங்கள் வருகையைப் பதிவு செய்து, பாதுகாவலரிடம் காட்ட அனுமதிச் சீட்டைப் பெறுங்கள்."],
  "Show your invitation QR, or scan your walk-in slip when you leave.": ["出示邀请二维码，或离开时扫描您的登记单。", "Tunjukkan QR jemputan anda, atau imbas slip daftar masuk anda semasa keluar.", "உங்கள் அழைப்பிதழ் QR-ஐக் காட்டுங்கள், அல்லது வெளியேறும்போது பதிவுச் சீட்டை ஸ்கேன் செய்யுங்கள்."],
  "Show the QR code from your invitation.": ["出示邀请中的二维码。", "Tunjukkan kod QR daripada jemputan anda.", "உங்கள் அழைப்பிதழில் உள்ள QR குறியீட்டைக் காட்டுங்கள்."],
  "Leaving? Scan your pass QR or enter its PIN.": ["要离开了？请扫描通行证二维码或输入密码。", "Mahu keluar? Imbas QR pas anda atau masukkan PINnya.", "வெளியேறுகிறீர்களா? அனுமதிச் சீட்டின் QR-ஐ ஸ்கேன் செய்யுங்கள் அல்லது PIN-ஐ உள்ளிடுங்கள்."],
  "Ask {name}": ["询问 {name}", "Tanya {name}", "{name}-இடம் கேளுங்கள்"],
  "Need help? Call the guardhouse": ["需要帮助？呼叫保安亭", "Perlu bantuan? Hubungi pondok pengawal", "உதவி வேண்டுமா? காவலர் அறையை அழைக்கவும்"],
  "Security answers by video.": ["保安会通过视频接听。", "Pengawal keselamatan menjawab melalui video.", "பாதுகாவலர் வீடியோ மூலம் பதிலளிப்பார்."],

  // Directory
  "Which unit are you visiting?": ["您要拜访哪个单位？", "Unit mana yang anda lawati?", "எந்த வீட்டுக்குச் செல்கிறீர்கள்?"],
  "All blocks": ["所有座", "Semua blok", "அனைத்து பிளாக்குகளும்"],
  "Unit number, e.g. 05-12 or 12A": ["单位号码，例如 05-12 或 12A", "Nombor unit, cth. 05-12 atau 12A", "வீட்டு எண், எ.கா. 05-12 அல்லது 12A"],
  "Type the unit number": ["输入单位号码", "Taip nombor unit", "வீட்டு எண்ணை உள்ளிடுங்கள்"],
  "Loading…": ["加载中…", "Memuatkan…", "ஏற்றுகிறது…"],
  "No unit matches. Check the number, or ask the guardhouse.": ["没有匹配的单位。请检查号码，或询问保安亭。", "Tiada unit yang sepadan. Semak nombor, atau tanya pondok pengawal.", "பொருந்தும் வீடு இல்லை. எண்ணைச் சரிபாருங்கள், அல்லது காவலர் அறையில் கேளுங்கள்."],
  "Matching units appear here as you type.": ["输入时，匹配的单位会显示在这里。", "Unit yang sepadan dipaparkan di sini semasa anda menaip.", "நீங்கள் உள்ளிடும்போது பொருந்தும் வீடுகள் இங்கே தோன்றும்."],
  "Unit": ["单位", "Unit", "வீடு"],
  "Keep typing to narrow it down.": ["继续输入以缩小范围。", "Teruskan menaip untuk mengecilkan carian.", "தேடலைக் குறைக்க தொடர்ந்து உள்ளிடுங்கள்."],
  "Clear": ["清除", "Padam", "அழி"],
  "Delete": ["删除", "Hapus", "நீக்கு"],
  "Use the number pad": ["使用数字键盘", "Guna pad nombor", "எண் விசைப்பலகையைப் பயன்படுத்துங்கள்"],
  "Unit has letters? Use keyboard": ["单位号码有字母？使用键盘", "Unit ada huruf? Guna papan kekunci", "வீட்டு எண்ணில் எழுத்துகள் உள்ளனவா? விசைப்பலகையைப் பயன்படுத்துங்கள்"],

  // Calling
  "Please see the guardhouse": ["请前往保安亭", "Sila ke pondok pengawal", "காவலர் அறைக்குச் செல்லுங்கள்"],
  "The security team will help you.": ["保安人员会协助您。", "Pasukan keselamatan akan membantu anda.", "பாதுகாப்புக் குழுவினர் உங்களுக்கு உதவுவார்கள்."],
  "Video intercom is not available right now.": ["视频对讲目前无法使用。", "Interkom video tidak tersedia sekarang.", "வீடியோ இண்டர்காம் இப்போது கிடைக்கவில்லை."],
  "Could not place the call": ["无法拨通", "Panggilan tidak dapat dibuat", "அழைப்பை மேற்கொள்ள முடியவில்லை"],
  "Do you need more time?": ["您需要更多时间吗？", "Perlukan lebih masa?", "உங்களுக்கு இன்னும் நேரம் வேண்டுமா?"],
  "Starting over in {s}s.": ["{s} 秒后重新开始。", "Bermula semula dalam {s} saat.", "{s} விநாடிகளில் மீண்டும் தொடங்கும்."],
  "Yes, I need more time": ["是的，我需要更多时间", "Ya, saya perlukan lebih masa", "ஆம், எனக்கு இன்னும் நேரம் வேண்டும்"],
  "Call ended": ["通话已结束", "Panggilan tamat", "அழைப்பு முடிந்தது"],
  "The resident left the call.": ["住户已离开通话。", "Penghuni telah meninggalkan panggilan.", "குடியிருப்பாளர் அழைப்பிலிருந்து வெளியேறினார்."],
  "Security left the call.": ["保安已离开通话。", "Pengawal keselamatan telah meninggalkan panggilan.", "பாதுகாவலர் அழைப்பிலிருந்து வெளியேறினார்."],
  "Welcome!": ["欢迎！", "Selamat datang!", "நல்வரவு!"],
  "{unit} has opened the gate for you.": ["{unit} 已为您开门。", "{unit} telah membuka pintu pagar untuk anda.", "{unit} உங்களுக்காக வாயிலைத் திறந்துள்ளது."],
  "The guardhouse has opened the gate for you.": ["保安亭已为您开门。", "Pondok pengawal telah membuka pintu pagar untuk anda.", "காவலர் அறை உங்களுக்காக வாயிலைத் திறந்துள்ளது."],
  "The resident declined": ["住户已拒绝", "Penghuni menolak", "குடியிருப்பாளர் மறுத்துவிட்டார்"],
  "Please contact the guardhouse if you need help.": ["如需帮助，请联系保安亭。", "Sila hubungi pondok pengawal jika anda perlukan bantuan.", "உதவி தேவைப்பட்டால் காவலர் அறையைத் தொடர்பு கொள்ளுங்கள்."],
  "The guardhouse ended the call": ["保安亭已结束通话", "Pondok pengawal menamatkan panggilan", "காவலர் அறை அழைப்பை முடித்தது"],
  "Please speak to security if you still need help.": ["如仍需帮助，请与保安联系。", "Sila bercakap dengan pengawal keselamatan jika anda masih perlukan bantuan.", "இன்னும் உதவி தேவைப்பட்டால் பாதுகாவலரிடம் பேசுங்கள்."],
  "No answer": ["无人接听", "Tiada jawapan", "பதில் இல்லை"],
  "Nobody picked up. You can try again or call the guardhouse.": ["无人接听。您可以再试一次或呼叫保安亭。", "Tiada siapa menjawab. Anda boleh cuba lagi atau hubungi pondok pengawal.", "யாரும் பதிலளிக்கவில்லை. மீண்டும் முயலலாம் அல்லது காவலர் அறையை அழைக்கலாம்."],
  "Nobody at the guardhouse picked up. Please try again in a moment.": ["保安亭无人接听。请稍后再试。", "Tiada siapa di pondok pengawal menjawab. Sila cuba lagi sebentar lagi.", "காவலர் அறையில் யாரும் பதிலளிக்கவில்லை. சிறிது நேரத்தில் மீண்டும் முயலுங்கள்."],
  "Connected. The resident can see and hear you.": ["已接通。住户可以看到并听到您。", "Bersambung. Penghuni boleh melihat dan mendengar anda.", "இணைக்கப்பட்டது. குடியிருப்பாளர் உங்களைப் பார்க்கவும் கேட்கவும் முடியும்."],
  "Connected. Security can see and hear you.": ["已接通。保安可以看到并听到您。", "Bersambung. Pengawal keselamatan boleh melihat dan mendengar anda.", "இணைக்கப்பட்டது. பாதுகாவலர் உங்களைப் பார்க்கவும் கேட்கவும் முடியும்."],
  "Ringing…": ["正在响铃…", "Sedang berdering…", "அழைக்கிறது…"],
  "Talking to": ["正在通话", "Bercakap dengan", "பேசுகிறீர்கள்"],
  "Calling": ["正在呼叫", "Memanggil", "அழைக்கிறது"],
  "Guardhouse": ["保安亭", "Pondok pengawal", "காவலர் அறை"],
  "Security": ["保安", "Keselamatan", "பாதுகாப்பு"],
  "Waiting for an answer · {s}s": ["等待接听 · {s} 秒", "Menunggu jawapan · {s} saat", "பதிலுக்குக் காத்திருக்கிறது · {s} வி"],
  "End call": ["结束通话", "Tamatkan panggilan", "அழைப்பை முடி"],

  // Been here before? / visitor details
  "Checking…": ["正在检查…", "Menyemak…", "சரிபார்க்கிறது…"],
  "Welcome back": ["欢迎回来", "Selamat kembali", "மீண்டும் நல்வரவு"],
  "Is this you?": ["这是您吗？", "Adakah ini anda?", "இது நீங்களா?"],
  "No, it's not me": ["不，不是我", "Bukan, itu bukan saya", "இல்லை, இது நான் அல்ல"],
  "Yes, continue": ["是的，继续", "Ya, teruskan", "ஆம், தொடரவும்"],
  "Been here before?": ["以前来过吗？", "Pernah datang sebelum ini?", "முன்பு இங்கு வந்திருக்கிறீர்களா?"],
  "Enter your mobile number or the last 4 characters of your NRIC/FIN to skip the form.": ["输入您的手机号码或 NRIC/FIN 最后 4 位，即可跳过表格。", "Masukkan nombor telefon bimbit anda atau 4 aksara terakhir NRIC/FIN untuk melangkau borang.", "படிவத்தைத் தவிர்க்க உங்கள் கைப்பேசி எண்ணை அல்லது NRIC/FIN-இன் கடைசி 4 எழுத்துகளை உள்ளிடுங்கள்."],
  "Continue": ["继续", "Teruskan", "தொடரவும்"],
  "First time here": ["第一次来", "Kali pertama di sini", "முதல் முறை வருகிறேன்"],
  "How we use your data": ["我们如何使用您的资料", "Cara kami menggunakan data anda", "உங்கள் தரவை நாங்கள் எவ்வாறு பயன்படுத்துகிறோம்"],
  "Hi {name}": ["{name}，您好", "Hai {name}", "வணக்கம் {name}"],
  "Register your visit": ["登记您的来访", "Daftar lawatan anda", "உங்கள் வருகையைப் பதிவு செய்யுங்கள்"],
  "Tell the resident who you are": ["告诉住户您是谁", "Beritahu penghuni siapa anda", "நீங்கள் யார் என்று குடியிருப்பாளரிடம் சொல்லுங்கள்"],
  "Visiting {unit}": ["拜访 {unit}", "Melawat {unit}", "{unit}-க்குச் செல்கிறீர்கள்"],
  "Your name": ["您的姓名", "Nama anda", "உங்கள் பெயர்"],
  "Visiting a resident": ["拜访住户", "Melawat penghuni", "குடியிருப்பாளரைப் பார்க்க"],
  "Parcel delivery": ["包裹派送", "Penghantaran bungkusan", "பார்சல் விநியோகம்"],
  "Food delivery": ["外卖派送", "Penghantaran makanan", "உணவு விநியோகம்"],
  "Contractor / service": ["承包商 / 服务", "Kontraktor / servis", "ஒப்பந்ததாரர் / சேவை"],
  "Pick-up / drop-off": ["接送", "Ambil / hantar", "ஏற்றுதல் / இறக்குதல்"],
  "Other": ["其他", "Lain-lain", "மற்றவை"],
  "Courier company, e.g. Ninja Van": ["快递公司，例如 Ninja Van", "Syarikat kurier, cth. Ninja Van", "கூரியர் நிறுவனம், எ.கா. Ninja Van"],
  "e.g. GrabFood, foodpanda, Deliveroo": ["例如 GrabFood、foodpanda、Deliveroo", "cth. GrabFood, foodpanda, Deliveroo", "எ.கா. GrabFood, foodpanda, Deliveroo"],
  "Company name": ["公司名称", "Nama syarikat", "நிறுவனப் பெயர்"],
  "e.g. Grab, Gojek, taxi": ["例如 Grab、Gojek、德士", "cth. Grab, Gojek, teksi", "எ.கா. Grab, Gojek, டாக்ஸி"],
  "Mobile (optional)": ["手机（选填）", "Telefon bimbit (pilihan)", "கைப்பேசி (விருப்பத்தேர்வு)"],
  "Last 4 of NRIC/FIN (optional)": ["NRIC/FIN 最后 4 位（选填）", "4 aksara terakhir NRIC/FIN (pilihan)", "NRIC/FIN கடைசி 4 (விருப்பத்தேர்வு)"],
  "Optional: lets you skip this form on your next visit. Only the last 4 characters of your NRIC/FIN are kept.": ["选填：下次来访时可跳过此表格。我们只保留 NRIC/FIN 的最后 4 位。", "Pilihan: membolehkan anda melangkau borang ini pada lawatan seterusnya. Hanya 4 aksara terakhir NRIC/FIN anda disimpan.", "விருப்பத்தேர்வு: அடுத்த வருகையில் இந்தப் படிவத்தைத் தவிர்க்கலாம். உங்கள் NRIC/FIN-இன் கடைசி 4 எழுத்துகள் மட்டுமே சேமிக்கப்படும்."],
  "Agree & get my pass": ["同意并领取通行证", "Setuju & dapatkan pas saya", "ஒப்புக்கொண்டு அனுமதிச் சீட்டைப் பெறு"],
  "Agree & call": ["同意并呼叫", "Setuju & panggil", "ஒப்புக்கொண்டு அழை"],
  "Next: photo": ["下一步：拍照", "Seterusnya: foto", "அடுத்து: புகைப்படம்"],

  // Photos and camera
  "Your photo": ["您的照片", "Foto anda", "உங்கள் புகைப்படம்"],
  "Happy with this photo?": ["对这张照片满意吗？", "Berpuas hati dengan foto ini?", "இந்தப் புகைப்படம் சரியா?"],
  "A quick photo please": ["请拍一张照片", "Sila ambil foto sebentar", "தயவுசெய்து ஒரு புகைப்படம்"],
  "Security uses it to check your pass.": ["保安会用它核对您的通行证。", "Pengawal keselamatan menggunakannya untuk menyemak pas anda.", "உங்கள் அனுமதிச் சீட்டைச் சரிபார்க்க பாதுகாவலர் இதைப் பயன்படுத்துவார்."],
  "The resident sees it before answering.": ["住户接听前会看到这张照片。", "Penghuni akan melihatnya sebelum menjawab.", "பதிலளிக்கும் முன் குடியிருப்பாளர் இதைப் பார்ப்பார்."],
  "You can also check out by looking at the kiosk camera when you leave. Only a face template made from this photo is kept, and it is deleted when you check out or your pass ends.": ["离开时，您也可以看着自助机摄像头完成离开登记。我们只保留由这张照片生成的人脸模板，并会在您离开登记或通行证到期时删除。", "Anda juga boleh daftar keluar dengan melihat kamera kiosk semasa keluar. Hanya templat wajah daripada foto ini disimpan, dan ia dipadam apabila anda daftar keluar atau pas anda tamat.", "வெளியேறும்போது கியோஸ்க் கேமராவைப் பார்த்தும் வெளியேறலாம். இந்தப் புகைப்படத்திலிருந்து உருவாக்கப்படும் முக வார்ப்புரு மட்டுமே சேமிக்கப்படும்; நீங்கள் வெளியேறும்போது அல்லது அனுமதிச் சீட்டு முடியும்போது அது நீக்கப்படும்."],
  "✓ Face check-out ready.": ["✓ 人脸离开登记已就绪。", "✓ Daftar keluar dengan wajah sedia.", "✓ முகம் மூலம் வெளியேறுதல் தயார்."],
  "We could not see your face clearly. Retake to use face check-out, or use the QR / PIN when you leave.": ["我们无法看清您的脸。请重拍以使用人脸离开登记，或离开时使用二维码 / 密码。", "Kami tidak dapat melihat wajah anda dengan jelas. Ambil semula untuk daftar keluar dengan wajah, atau guna QR / PIN semasa keluar.", "உங்கள் முகம் தெளிவாகத் தெரியவில்லை. முகம் மூலம் வெளியேற மீண்டும் எடுங்கள், அல்லது வெளியேறும்போது QR / PIN-ஐப் பயன்படுத்துங்கள்."],
  "Checking the photo…": ["正在检查照片…", "Menyemak foto…", "புகைப்படத்தைச் சரிபார்க்கிறது…"],
  "Retake": ["重拍", "Ambil semula", "மீண்டும் எடு"],
  "Take photo": ["拍照", "Ambil foto", "புகைப்படம் எடு"],
  "Camera not available. Allow camera access for this site.": ["摄像头不可用。请允许此网站使用摄像头。", "Kamera tidak tersedia. Benarkan akses kamera untuk laman ini.", "கேமரா கிடைக்கவில்லை. இந்தத் தளத்துக்குக் கேமரா அனுமதி வழங்குங்கள்."],
  "Show your invitation or slip QR code": ["出示邀请或登记单二维码", "Tunjukkan kod QR jemputan atau slip anda", "உங்கள் அழைப்பிதழ் அல்லது சீட்டின் QR குறியீட்டைக் காட்டுங்கள்"],
  "Show your invitation QR code": ["出示邀请二维码", "Tunjukkan kod QR jemputan anda", "உங்கள் அழைப்பிதழ் QR குறியீட்டைக் காட்டுங்கள்"],
  "Hold your phone or your walk-in slip up to the camera.": ["将手机或登记单对准摄像头。", "Halakan telefon atau slip daftar masuk anda ke kamera.", "உங்கள் கைப்பேசியை அல்லது பதிவுச் சீட்டைக் கேமராவின் முன் காட்டுங்கள்."],
  "Hold your phone up to the camera.": ["将手机对准摄像头。", "Halakan telefon anda ke kamera.", "உங்கள் கைப்பேசியைக் கேமராவின் முன் காட்டுங்கள்."],
  "Hi {name}, a quick photo please": ["{name}，您好，请拍一张照片", "Hai {name}, sila ambil foto sebentar", "வணக்கம் {name}, தயவுசெய்து ஒரு புகைப்படம்"],
  "This invitation asks for a face photo. It is kept with the entry record for security.": ["此邀请需要人脸照片。照片会与进入记录一起保存，以确保安全。", "Jemputan ini memerlukan foto wajah. Ia disimpan bersama rekod masuk untuk keselamatan.", "இந்த அழைப்பிதழுக்கு முகப் புகைப்படம் தேவை. பாதுகாப்புக்காக அது நுழைவுப் பதிவுடன் சேமிக்கப்படும்."],
  "A face template made from it also lets you check out by face; it is deleted when you check out or your pass ends.": ["由它生成的人脸模板也让您可以刷脸离开登记；在您离开登记或通行证到期时删除。", "Templat wajah daripadanya juga membolehkan anda daftar keluar dengan wajah; ia dipadam apabila anda daftar keluar atau pas anda tamat.", "அதிலிருந்து உருவாகும் முக வார்ப்புரு மூலம் முகத்தால் வெளியேறலாம்; நீங்கள் வெளியேறும்போது அல்லது அனுமதிச் சீட்டு முடியும்போது அது நீக்கப்படும்."],

  // Results and passes
  "Done": ["完成", "Selesai", "முடிந்தது"],
  "Could not register your visit": ["无法登记您的来访", "Lawatan anda tidak dapat didaftarkan", "உங்கள் வருகையைப் பதிவு செய்ய முடியவில்லை"],
  "Registering your visit…": ["正在登记您的来访…", "Mendaftarkan lawatan anda…", "உங்கள் வருகையைப் பதிவு செய்கிறது…"],
  "Your pass number": ["您的通行证号码", "Nombor pas anda", "உங்கள் அனுமதிச் சீட்டு எண்"],
  "Take your slip from the printer": ["请从打印机取走您的通行单", "Ambil slip anda dari pencetak", "அச்சுப்பொறியிலிருந்து உங்கள் சீட்டை எடுத்துக்கொள்ளுங்கள்"],
  "Take a photo or screenshot of this screen": ["请拍下或截图此画面", "Ambil foto atau tangkapan skrin paparan ini", "இந்தத் திரையைப் புகைப்படம் அல்லது ஸ்கிரீன்ஷாட் எடுங்கள்"],
  "Show it to security.": ["请出示给保安。", "Tunjukkannya kepada pengawal keselamatan.", "அதைப் பாதுகாவலரிடம் காட்டுங்கள்."],
  "You need the QR code or PIN to check out at the kiosk when you leave, and to get to the unit where the building has unit access control. Valid today until {time}.": ["离开时需要用二维码或密码在自助机离开登记；若大楼设有单位门禁，也需要它才能到达单位。今天 {time} 前有效。", "Anda memerlukan kod QR atau PIN untuk daftar keluar di kiosk semasa keluar, dan untuk ke unit jika bangunan mempunyai kawalan akses unit. Sah hari ini sehingga {time}.", "வெளியேறும்போது கியோஸ்கில் வெளியேறவும், கட்டடத்தில் வீட்டு அணுகல் கட்டுப்பாடு இருந்தால் வீட்டுக்குச் செல்லவும் QR குறியீடு அல்லது PIN தேவை. இன்று {time} வரை செல்லுபடியாகும்."],
  "Print again": ["再次打印", "Cetak semula", "மீண்டும் அச்சிடு"],
  "Print slip": ["打印通行单", "Cetak slip", "சீட்டை அச்சிடு"],
  "Back to the start in {s}s": ["{s} 秒后返回首页", "Kembali ke permulaan dalam {s} saat", "{s} விநாடிகளில் தொடக்கத்துக்குத் திரும்பும்"],
  "PIN": ["密码", "PIN", "PIN"],
  "Welcome! {unit} has opened the gate for you.": ["欢迎！{unit} 已为您开门。", "Selamat datang! {unit} telah membuka pintu pagar untuk anda.", "நல்வரவு! {unit} உங்களுக்காக வாயிலைத் திறந்துள்ளது."],
  "Welcome, {name}!": ["欢迎，{name}！", "Selamat datang, {name}!", "நல்வரவு, {name}!"],
  "The gate is opening. You are visiting {unit}.": ["大门正在打开。您正在拜访 {unit}。", "Pintu pagar sedang dibuka. Anda melawat {unit}.", "வாயில் திறக்கிறது. நீங்கள் {unit}-க்குச் செல்கிறீர்கள்."],
  "Entry not allowed": ["不允许进入", "Masuk tidak dibenarkan", "நுழைவு அனுமதிக்கப்படவில்லை"],
  "Something went wrong": ["出了点问题", "Sesuatu tidak kena", "ஏதோ தவறு நடந்தது"],

  // Check-out
  "Scan the QR code on your pass, enter its 4-digit PIN, or use your face.": ["扫描通行证上的二维码、输入 4 位密码，或刷脸。", "Imbas kod QR pada pas anda, masukkan PIN 4 digitnya, atau guna wajah anda.", "அனுமதிச் சீட்டிலுள்ள QR குறியீட்டை ஸ்கேன் செய்யுங்கள், 4 இலக்க PIN-ஐ உள்ளிடுங்கள், அல்லது உங்கள் முகத்தைப் பயன்படுத்துங்கள்."],
  "Scan the QR code on your pass, or enter its 4-digit PIN.": ["扫描通行证上的二维码，或输入 4 位密码。", "Imbas kod QR pada pas anda, atau masukkan PIN 4 digitnya.", "அனுமதிச் சீட்டிலுள்ள QR குறியீட்டை ஸ்கேன் செய்யுங்கள், அல்லது 4 இலக்க PIN-ஐ உள்ளிடுங்கள்."],
  "Scan QR or use your face": ["扫描二维码或刷脸", "Imbas QR atau guna wajah anda", "QR-ஐ ஸ்கேன் செய்யுங்கள் அல்லது முகத்தைப் பயன்படுத்துங்கள்"],
  "Scan QR": ["扫描二维码", "Imbas QR", "QR-ஐ ஸ்கேன் செய்"],
  "Look at the camera…": ["请看摄像头…", "Lihat ke kamera…", "கேமராவைப் பாருங்கள்…"],
  "Hold your slip, or the photo of your pass, up to the camera.": ["将通行单或通行证照片对准摄像头。", "Halakan slip anda, atau foto pas anda, ke kamera.", "உங்கள் சீட்டை அல்லது அனுமதிச் சீட்டின் புகைப்படத்தைக் கேமராவின் முன் காட்டுங்கள்."],
  "Recognising…": ["正在识别…", "Mengecam…", "அடையாளம் காண்கிறது…"],
  "Check out with my face": ["刷脸离开登记", "Daftar keluar dengan wajah saya", "என் முகத்தால் வெளியேறு"],
  "Enter PIN": ["输入密码", "Masukkan PIN", "PIN-ஐ உள்ளிடு"],
  "No clear face found. Look straight at the camera, or use your QR / PIN.": ["未检测到清晰的人脸。请正视摄像头，或使用二维码 / 密码。", "Tiada wajah yang jelas dikesan. Pandang terus ke kamera, atau guna QR / PIN anda.", "தெளிவான முகம் கிடைக்கவில்லை. கேமராவை நேராகப் பாருங்கள், அல்லது QR / PIN-ஐப் பயன்படுத்துங்கள்."],
  "Goodbye, {name}!": ["再见，{name}！", "Selamat jalan, {name}!", "சென்று வாருங்கள், {name}!"],
  "Pass {pass} checked out at {time}. Thank you for visiting.": ["通行证 {pass} 已于 {time} 离开登记。感谢您的来访。", "Pas {pass} didaftar keluar pada {time}. Terima kasih kerana melawat.", "அனுமதிச் சீட்டு {pass} {time}-க்கு வெளியேற்றப்பட்டது. வருகைக்கு நன்றி."],
  "Already checked out": ["已离开登记", "Sudah didaftar keluar", "ஏற்கனவே வெளியேறியாகிவிட்டது"],
  "Pass {pass} was checked out at {time}.": ["通行证 {pass} 已于 {time} 离开登记。", "Pas {pass} telah didaftar keluar pada {time}.", "அனுமதிச் சீட்டு {pass} {time}-க்கு வெளியேற்றப்பட்டது."],
  "Face not recognised": ["无法识别人脸", "Wajah tidak dikenali", "முகம் அடையாளம் காணப்படவில்லை"],
  "We could not tell you apart from another visitor. Please use your QR or PIN.": ["我们无法将您与另一位访客区分。请使用二维码或密码。", "Kami tidak dapat membezakan anda daripada pelawat lain. Sila guna QR atau PIN anda.", "உங்களை மற்றொரு வருகையாளரிடமிருந்து வேறுபடுத்த முடியவில்லை. உங்கள் QR அல்லது PIN-ஐப் பயன்படுத்துங்கள்."],
  "We could not recognise you. Try again facing the camera, or use your QR or PIN.": ["我们无法识别您。请面向摄像头再试一次，或使用二维码或密码。", "Kami tidak dapat mengecam anda. Cuba lagi sambil menghadap kamera, atau guna QR atau PIN anda.", "உங்களை அடையாளம் காண முடியவில்லை. கேமராவைப் பார்த்தபடி மீண்டும் முயலுங்கள், அல்லது QR அல்லது PIN-ஐப் பயன்படுத்துங்கள்."],
  "Wrong PIN": ["密码错误", "PIN salah", "தவறான PIN"],
  "That PIN does not match anyone on site. Please try again.": ["该密码与现场任何访客都不符。请再试一次。", "PIN itu tidak sepadan dengan sesiapa di premis. Sila cuba lagi.", "அந்த PIN வளாகத்தில் உள்ள யாருடனும் பொருந்தவில்லை. மீண்டும் முயலுங்கள்."],
  "Too many attempts": ["尝试次数过多", "Terlalu banyak cubaan", "அதிகமான முயற்சிகள்"],
  "Please wait a minute, or see the guardhouse.": ["请稍等一分钟，或前往保安亭。", "Sila tunggu seminit, atau ke pondok pengawal.", "ஒரு நிமிடம் காத்திருங்கள், அல்லது காவலர் அறைக்குச் செல்லுங்கள்."],
  "Unknown pass": ["未知通行证", "Pas tidak dikenali", "அறியப்படாத அனுமதிச் சீட்டு"],
  "Please see the guardhouse.": ["请前往保安亭。", "Sila ke pondok pengawal.", "காவலர் அறைக்குச் செல்லுங்கள்."],

  // Assistant
  "Starting…": ["正在启动…", "Memulakan…", "தொடங்குகிறது…"],
  "Listening… just speak": ["正在聆听…请直接说", "Mendengar… bercakap sahaja", "கேட்கிறது… பேசுங்கள்"],
  "I'm listening": ["我在听", "Saya sedang mendengar", "நான் கேட்கிறேன்"],
  "Thinking…": ["思考中…", "Berfikir…", "யோசிக்கிறது…"],
  "Speaking": ["正在说话", "Bercakap", "பேசுகிறது"],
  "Tap the microphone to talk": ["点击麦克风说话", "Ketik mikrofon untuk bercakap", "பேச மைக்ரோஃபோனைத் தட்டுங்கள்"],
  "Goodbye": ["再见", "Selamat tinggal", "சென்று வாருங்கள்"],
  "Ask about directions, facilities, parking, deliveries, or registering your visit.": ["可询问路线、设施、停车、派送或登记来访。", "Tanya tentang arah, kemudahan, tempat letak kereta, penghantaran, atau pendaftaran lawatan anda.", "வழி, வசதிகள், வாகன நிறுத்தம், விநியோகம் அல்லது வருகைப் பதிவு பற்றிக் கேளுங்கள்."],
  "Or type your question": ["或输入您的问题", "Atau taip soalan anda", "அல்லது உங்கள் கேள்வியை உள்ளிடுங்கள்"],
  "Close": ["关闭", "Tutup", "மூடு"],
  "Talk": ["说话", "Bercakap", "பேசு"],
  "Send": ["发送", "Hantar", "அனுப்பு"],
  "Map": ["地图", "Peta", "வரைபடம்"],
  "Hide map": ["隐藏地图", "Sembunyikan peta", "வரைபடத்தை மறை"],
  "The microphone is not available.": ["麦克风不可用。", "Mikrofon tidak tersedia.", "மைக்ரோஃபோன் கிடைக்கவில்லை."],
  "The assistant could not connect.": ["助手无法连接。", "Pembantu tidak dapat bersambung.", "உதவியாளரால் இணைக்க முடியவில்லை."],
  "Answers come from an AI (OpenAI) and may be imperfect. Your voice is processed only to answer you; the conversation is not stored.": ["回答由人工智能（OpenAI）生成，可能不完全准确。您的语音仅用于回答您；对话不会被保存。", "Jawapan dihasilkan oleh AI (OpenAI) dan mungkin tidak sempurna. Suara anda diproses hanya untuk menjawab anda; perbualan tidak disimpan.", "பதில்கள் AI (OpenAI) மூலம் வருகின்றன, முழுமையாகச் சரியாக இல்லாமல் இருக்கலாம். உங்கள் குரல் உங்களுக்குப் பதிலளிக்க மட்டுமே பயன்படுத்தப்படும்; உரையாடல் சேமிக்கப்படாது."],
};

const COLUMN: Record<Exclude<Lang, "en">, number> = { zh: 0, ms: 1, ta: 2 };

export function translate(lang: Lang, text: string, vars?: Vars): string {
  const out = lang === "en" ? text : STRINGS[text]?.[COLUMN[lang]] ?? text;
  return vars ? out.replace(/\{(\w+)\}/g, (all, key: string) => (key in vars ? String(vars[key]) : all)) : out;
}

export const LangContext = createContext<Lang>("en");
/** Set by the kiosk app so the language button in every screen's header can change it. */
export const SetLangContext = createContext<((lang: Lang) => void) | null>(null);

export const useLang = () => useContext(LangContext);

export const localeOf = (lang: Lang) => LANGS.find((l) => l.code === lang)!.locale;

export function useT(): Translate {
  const lang = useContext(LangContext);
  return useCallback((text: string, vars?: Vars) => translate(lang, text, vars), [lang]);
}
