# Phát hành (release) — Sepia Android

Dự án **không lên store**; phân phối bằng **GitHub Release đính APK** để tự cài trên máy (dogfood).
Đẩy tag `vX.Y.Z` → workflow [`.github/workflows/release.yml`](../.github/workflows/release.yml) build
APK **đã ký** (app **lõi**, không nhúng sách — ADR-010) rồi tạo Release đính APK.

## Lần đầu: tạo keystore + nạp secret (làm MỘT lần, giữ mãi)

> ⚠️ Chữ ký APK **dính vĩnh viễn**: các bản sau phải ký cùng keystore mới cài **đè** được (giữ dữ
> liệu đọc/highlight). **Mất keystore hoặc mật khẩu = không ship update đè được nữa** → backup file
> `.jks` + mật khẩu ở nơi an toàn (không trong repo).

### 1. Sinh keystore

```bash
keytool -genkeypair -v \
  -keystore sepia-release.jks \
  -alias sepia \
  -keyalg RSA -keysize 2048 -validity 10000
# Nhập mật khẩu store (và key, có thể để trùng). Ghi nhớ: alias = "sepia".
```

### 2. Nạp 4 secret lên GitHub

`Settings → Secrets and variables → Actions → New repository secret`:

| Secret | Giá trị |
|---|---|
| `RELEASE_KEYSTORE_BASE64` | `base64 -i sepia-release.jks` (dán toàn bộ chuỗi) |
| `RELEASE_STORE_PASSWORD` | mật khẩu store ở bước 1 |
| `RELEASE_KEY_ALIAS` | `sepia` |
| `RELEASE_KEY_PASSWORD` | mật khẩu key ở bước 1 |

Hoặc bằng CLI:

```bash
gh secret set RELEASE_KEYSTORE_BASE64 < <(base64 -i sepia-release.jks)
gh secret set RELEASE_STORE_PASSWORD   # rồi dán mật khẩu
gh secret set RELEASE_KEY_ALIAS -b sepia
gh secret set RELEASE_KEY_PASSWORD     # rồi dán mật khẩu
```

> Thiếu secret → APK vẫn build nhưng **CHƯA ký** (không cài đè cập nhật được).

## Mỗi release

1. **Bump version** trong [`androidApp/build.gradle.kts`](../androidApp/build.gradle.kts):
   `versionName = "X.Y.Z"` và `versionCode` **tăng** (vd 1 → 2). Commit + PR, chờ CI xanh, merge master.
2. **Tag + đẩy** từ master mới nhất:
   ```bash
   git checkout master && git pull
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```
3. **CI lo phần còn lại**: `release.yml` build APK đã ký → tạo Release `vX.Y.Z` đính `sepia-vX.Y.Z.apk`
   (release notes tự gom từ PR/commit). Theo dõi: `gh run list --workflow=release.yml`.
4. **Cài máy**: tải APK từ trang Release, hoặc `adb install -r sepia-vX.Y.Z.apk`.

## Build cục bộ kèm gói sách (Đông Y) — không qua CI

CI chỉ ra app lõi (sách không vào git/CI). Muốn APK nhúng sẵn sách để dùng ngay:

```bash
# 1) đóng gói sách (PDF trong samples/ ở gốc repo)
cd pdf-pipeline && uv run sepia-pipeline pack ../samples --out ../.content-pack && cd ..
# 2) build APK release nhúng gói (cần keystore.properties cục bộ để ký, xem dưới)
./gradlew :androidApp:assembleRelease -Psepia.contentDir="$PWD/.content-pack"
adb install -r androidApp/build/outputs/apk/release/androidApp-release.apk
```

Ký release cục bộ: tạo `keystore.properties` (gitignored) ở gốc repo:

```properties
storeFile=/duong/dan/tuyet-doi/sepia-release.jks
storePassword=...
keyAlias=sepia
keyPassword=...
```

(Thiếu file này thì `assembleRelease` cục bộ ra APK chưa ký — chỉ build thử được, không cài đè.)
