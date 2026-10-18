# creatorloop

**Instagram mualliflari uchun ochiq kodli AI kontent studiyasi: Claude va rasmiy Instagram API asosida.**

Nima ishlayotganini tahlil qilish → Reels va karusellar yaratish → joylash yoki navbatga qoʻyish →
24 va 72 soatdan keyin natijani koʻrib chiqish. Hammasi Claude bilan suhbatda.

- **Taxmin emas, raqamlar:** eng yaxshi va eng yomon postlar birinchi qatori (hook) bilan, formatlar taqqoslash, har 1000 qamrovga
  obunachilar, Reels koʻrish vaqti, eng yaxshi kun va soat, qaysi izohlar (caption) ishlaydi.
- **Raqobatchilar — qonuniy:** kuzatish, obunachilar tarixi, akkaunt medianasidan N barobar koʻp yigʻgan postlar,
  istalgan ochiq postni havola orqali tahlil qilish.
- **Kontent yaratish:** Remotion asosidagi Reels shabloni, avtomatik tekshiruvlar, oʻz musiqasi, litsenziyali 3D obyektlar.
- **Xavfsiz joylash:** har bir postdan oldin koʻrib chiqish (preview), oʻzgargan fayllardan himoyalangan navbat,
  24/72 soatlik hisobotlar, izohlarga javob — faqat sizning roziligingizdan keyin.
- **Faqat rasmiy API:** skreyping yoʻq, akkaunt uchun xavf yoʻq.

## Tez boshlash

Kerak boʻladi: [uv](https://docs.astral.sh/uv/getting-started/installation/), Claude Desktop, **Business** yoki
**Creator** turidagi Instagram akkaunt, unga ulangan **Facebook sahifa** va oʻzingizning Meta ilovangiz
([qoʻllanma, ingliz tilida](docs/meta-setup.md)).

```bash
uvx --from creatorloop creatorloop-setup
```

Buyruq Claude Desktop'ni ulaydi va brauzerda sozlash sahifasini ochadi: ilovangizning **App ID** va **App Secret**
qiymatlarini kiriting, **“Facebook orqali davom etish”** tugmasini bosing — tayyor. Soʻng Claude'dan soʻrang:
*«Oxirgi 10 ta postim qanday ketdi va keyin nima joylashim kerak?»* Claude'dasizmi? *«Instagram'imni ulab ber»* deb
soʻrang — oʻsha sahifa ochiladi. Secret va token faqat shu sahifada kiritiladi, chatga emas.

### Bir bosishda oʻrnatish (Claude Desktop)

Terminal ochishni xohlamaysizmi? [Soʻnggi reliz](https://github.com/pandich93/creatorloop/releases/latest)dan
`.mcpb` faylini yuklab oling va ustiga ikki marta bosing (yoki Claude Desktop → Settings → Extensions oynasiga sudrab
olib keling). Python va kutubxonalarni Claude Desktop oʻzi oʻrnatadi, shuning uchun birinchi ishga tushirish bir
daqiqacha vaqt oladi. Ikkita ixtiyoriy maydonni boʻsh qoldiring va Claude'dan *«Instagram'imni ulab ber»* deb
soʻrang — oʻsha sozlash sahifasi ochiladi. Ularni faqat tokeningiz va akkaunt ID'ingiz allaqachon boʻlsa toʻldiring:
bu maydonlardagi qiymatlar sozlash sahifasidan ustun turadi. Claude Desktop `uv`ni topa olmasa,
[uv](https://docs.astral.sh/uv/getting-started/installation/)ni oʻrnating va Claude Desktop'ni qayta ishga tushiring.

Toʻliq hujjatlar — [ingliz tilidagi README](README.md)da.

Mustaqil ochiq kodli loyiha, Meta va Instagram bilan bogʻliq emas. Litsenziya: [MIT](LICENSE).
