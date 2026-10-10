# TestFlight / App Store build

Slim target: only `ios/main.m`, `ios/OEWebGame.m`, the web bundle (`ios/WebGame`, shipped as
`open-empire-mobile`) and the asset catalog. No SDL, no OpenEmpire engine, no 0 A.D. models.

    cd release && xcodegen                      # regenerates MedievalAges.xcodeproj
    xcodebuild -project MedievalAges.xcodeproj -scheme MedievalAges -configuration Release \
      -destination 'generic/platform=iOS' -archivePath /tmp/MA.xcarchive archive
    xcodebuild -exportArchive -archivePath /tmp/MA.xcarchive -exportOptionsPlist ExportOptions.plist -exportPath /tmp/ipa
    xcrun altool --upload-app -f "/tmp/ipa/Medieval Ages.ipa" -t ios --apiKey $KEY_ID --apiIssuer $ISSUER

Bump `CURRENT_PROJECT_VERSION` in `project.yml` for every upload. Bundle ID
`com.nathanaelguitar.medievalages`, profile "Medieval Ages App Store 2026-10-10" (created via the
App Store Connect API; the Xcode account path cannot sign). The dev build in `build-ios/`
(`com.nathanaelguitar.openempire`) is a separate app on the phone.
