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
uvx --from creatorloop creatorloop-auth exchange --short-token <TOKEN> --write
uvx --from creatorloop creatorloop-auth whoami --write
```

Ikkinchi buyruqdan oldin birinchi buyruq koʻrsatgan sozlamalar fayliga `META_APP_ID` va `META_APP_SECRET` ni yozing.
Claude Desktop'ni qayta ishga tushiring va soʻrang: *«Oxirgi 10 ta postim qanday ketdi va keyin nima joylashim kerak?»*

Toʻliq hujjatlar — [ingliz tilidagi README](README.md)da.

Mustaqil ochiq kodli loyiha, Meta va Instagram bilan bogʻliq emas. Litsenziya: [MIT](LICENSE).
