/* SPDX-License-Identifier: GPL-3.0-or-later */
#import <UIKit/UIKit.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#include <SDL_syswm.h>
#include <math.h>
#include <stdlib.h>
#include "OEMobile.h"
#include "OEAssets.h"
#import "OEArtDemo.h"
#import "OEWebGame.h"

@interface OEGameTouchView : UIView
@end
@implementation OEGameTouchView
- (instancetype)initWithFrame:(CGRect)frame {
    if ((self=[super initWithFrame:frame])) {
        self.multipleTouchEnabled=YES; self.backgroundColor=UIColor.clearColor;
        self.accessibilityLabel=@"Game map. Tap to select. Hold to issue an order. Two fingers pan.";
    }
    return self;
}
- (CGPoint)logicalPoint:(UITouch *)touch {
    CGPoint p=[touch locationInView:self];
    int w=0,h=0; SDL_GetWindowSize(OEApp_Window(),&w,&h);
    float x=0,y=0;
    int windowX=(int)lround(p.x*w/MAX(1.0,self.bounds.size.width));
    int windowY=(int)lround(p.y*h/MAX(1.0,self.bounds.size.height));
    SDL_RenderWindowToLogical(OEApp_Renderer(),windowX,windowY,&x,&y);
    return CGPointMake(x,y);
}
- (void)touchesBegan:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    (void)event;
    for (UITouch *touch in touches) {
        CGPoint p=[self logicalPoint:touch];
        if (p.x>=0 && p.y>=0 && p.x<OE_WIDTH && p.y<OE_HEIGHT)
            OEInput_Begin((int64_t)(uintptr_t)(__bridge void *)touch,p.x,p.y,touch.timestamp);
    }
}
- (void)touchesMoved:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    (void)event;
    for (UITouch *touch in touches) {
        CGPoint p=[self logicalPoint:touch];
        OEInput_Move((int64_t)(uintptr_t)(__bridge void *)touch,p.x,p.y);
    }
}
- (void)touchesEnded:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    (void)event;
    for (UITouch *touch in touches) {
        CGPoint p=[self logicalPoint:touch];
        OEInput_End((int64_t)(uintptr_t)(__bridge void *)touch,p.x,p.y,touch.timestamp);
    }
}
- (void)touchesCancelled:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    (void)touches; (void)event; OEInput_Reset();
}
@end

@interface OEPlatformController : NSObject <UIDocumentPickerDelegate>
@property(nonatomic,strong) UIViewController *root;
@property(nonatomic,strong) UIView *launcher;
@property(nonatomic,strong) UIStackView *launcherStack;
@property(nonatomic,strong) UILabel *message;
@property(nonatomic,strong) UIButton *playButton;
@property(nonatomic,strong) UIButton *importButton;
@property(nonatomic,strong) UIActivityIndicatorView *spinner;
@property(nonatomic,strong) OEGameTouchView *gameTouch;
@property(nonatomic,strong) UIStackView *toolbar;
@property(nonatomic,strong) UILabel *hint;
@property(nonatomic,strong) NSURL *dataURL;
@property(nonatomic,strong) OEArtDemo *artDemo;
@property(nonatomic,strong) OEWebGame *webGame;
@property(nonatomic) BOOL importing;
- (void)showLauncher:(NSString *)message;
- (void)showLoading;
- (void)showGame;
- (void)showPaused;
@end
static OEPlatformController *platform;

static UIColor *PanelColor(void) { return [UIColor colorWithRed:0.055 green:0.08 blue:0.11 alpha:0.96]; }
static UIButton *Button(NSString *title, id target, SEL selector) {
    UIButton *button=[UIButton buttonWithType:UIButtonTypeSystem];
    UIButtonConfiguration *config=[UIButtonConfiguration filledButtonConfiguration];
    config.title=title; config.baseBackgroundColor=[UIColor colorWithRed:0.16 green:0.25 blue:0.31 alpha:1];
    config.baseForegroundColor=UIColor.whiteColor;
    config.contentInsets=NSDirectionalEdgeInsetsMake(11,14,11,14);
    config.cornerStyle=UIButtonConfigurationCornerStyleMedium;
    button.configuration=config;
    [button addTarget:target action:selector forControlEvents:UIControlEventTouchUpInside];
    button.accessibilityLabel=title;
    return button;
}

@implementation OEPlatformController
- (instancetype)initWithWindow:(SDL_Window *)window {
    if (!(self=[super init])) return nil;
    SDL_SysWMinfo info; SDL_VERSION(&info.version);
    if (!SDL_GetWindowWMInfo(window,&info)) return nil;
    UIWindow *uiWindow=info.info.uikit.window;
    self.root=uiWindow.rootViewController;
    UIView *view=self.root.view;
    view.backgroundColor=PanelColor();
    self.root.overrideUserInterfaceStyle=UIUserInterfaceStyleDark;
    NSFileManager *fm=NSFileManager.defaultManager;
    NSURL *support=[fm URLForDirectory:NSApplicationSupportDirectory inDomain:NSUserDomainMask appropriateForURL:nil create:YES error:nil];
    self.dataURL=[support URLByAppendingPathComponent:@"GameData" isDirectory:YES];
    self.artDemo=[OEArtDemo new];
    self.webGame=[OEWebGame new];
    __weak OEPlatformController *weakSelf=self;
    self.artDemo.onEnd=^{ [weakSelf showLauncher:@"Sandbox ended. Start again to return to the bundled 0 A.D. scene."]; };
    self.gameTouch=[[OEGameTouchView alloc] initWithFrame:view.bounds];
    self.gameTouch.autoresizingMask=UIViewAutoresizingFlexibleWidth|UIViewAutoresizingFlexibleHeight;
    [view addSubview:self.gameTouch];
    self.toolbar=[[UIStackView alloc] initWithArrangedSubviews:@[
        Button(@"Select",self,@selector(selectMode)), Button(@"Order",self,@selector(orderMode)),
        Button(@"Pan",self,@selector(panMode)), Button(@"Actions",self,@selector(showActions)),
        Button(@"Map",self,@selector(toggleMap)), Button(@"Menu",self,@selector(showPaused))
    ]];
    self.toolbar.axis=UILayoutConstraintAxisHorizontal; self.toolbar.spacing=6;
    self.toolbar.distribution=UIStackViewDistributionFillEqually;
    self.toolbar.translatesAutoresizingMaskIntoConstraints=NO;
    [view addSubview:self.toolbar];
    self.hint=[UILabel new]; self.hint.numberOfLines=2;
    self.hint.font=[UIFont systemFontOfSize:12 weight:UIFontWeightMedium];
    self.hint.textColor=UIColor.whiteColor; self.hint.backgroundColor=PanelColor();
    self.hint.layer.cornerRadius=6; self.hint.clipsToBounds=YES;
    self.hint.textAlignment=NSTextAlignmentCenter; self.hint.translatesAutoresizingMaskIntoConstraints=NO;
    [view addSubview:self.hint];
    UILayoutGuide *safe=view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [self.toolbar.centerXAnchor constraintEqualToAnchor:safe.centerXAnchor],
        [self.toolbar.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor constant:-6],
        [self.toolbar.widthAnchor constraintLessThanOrEqualToConstant:660],
        [self.toolbar.leadingAnchor constraintGreaterThanOrEqualToAnchor:safe.leadingAnchor constant:8],
        [self.toolbar.trailingAnchor constraintLessThanOrEqualToAnchor:safe.trailingAnchor constant:-8],
        [self.toolbar.heightAnchor constraintGreaterThanOrEqualToConstant:44],
        [self.hint.leadingAnchor constraintEqualToAnchor:self.toolbar.leadingAnchor],
        [self.hint.trailingAnchor constraintEqualToAnchor:self.toolbar.trailingAnchor],
        [self.hint.bottomAnchor constraintEqualToAnchor:self.toolbar.topAnchor constant:-4],
        [self.hint.heightAnchor constraintGreaterThanOrEqualToConstant:30]
    ]];
    NSLayoutConstraint *preferredWidth=[self.toolbar.widthAnchor constraintEqualToAnchor:safe.widthAnchor constant:-16];
    preferredWidth.priority=UILayoutPriorityDefaultHigh; preferredWidth.active=YES;
    [self buildLauncher];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(willResign:) name:UIApplicationWillResignActiveNotification object:nil];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(didBecome:) name:UIApplicationDidBecomeActiveNotification object:nil];
    /* Pocket Empires is the whole experience, so open straight into the bundled web game
       instead of parking the player on the native launcher. The launcher is still built but
       immediately hidden: it remains the message surface for the legacy native port. The
       start is deferred one runloop turn so the web view is laid out at its real size. */
    dispatch_async(dispatch_get_main_queue(), ^{ [self start]; });
    return self;
}
- (void)buildLauncher {
    UIView *view=self.root.view;
    self.launcher=[UIView new]; self.launcher.backgroundColor=PanelColor();
    self.launcher.translatesAutoresizingMaskIntoConstraints=NO; [view addSubview:self.launcher];
    [NSLayoutConstraint activateConstraints:@[
        [self.launcher.leadingAnchor constraintEqualToAnchor:view.leadingAnchor],
        [self.launcher.trailingAnchor constraintEqualToAnchor:view.trailingAnchor],
        [self.launcher.topAnchor constraintEqualToAnchor:view.topAnchor],
        [self.launcher.bottomAnchor constraintEqualToAnchor:view.bottomAnchor]
    ]];
    UILabel *title=[UILabel new]; title.text=@"OPENEMPIRE";
    title.font=[UIFont systemFontOfSize:32 weight:UIFontWeightBold]; title.textAlignment=NSTextAlignmentCenter;
    UILabel *subtitle=[UILabel new]; subtitle.text=@"Original C engine. Native touch controls. Offline sandbox.";
    subtitle.font=[UIFont systemFontOfSize:14 weight:UIFontWeightMedium]; subtitle.textAlignment=NSTextAlignmentCenter; subtitle.numberOfLines=2;
    self.message=[UILabel new]; self.message.numberOfLines=0;
    self.message.font=[UIFont systemFontOfSize:14]; self.message.textAlignment=NSTextAlignmentCenter;
    self.message.textColor=[UIColor colorWithWhite:0.8 alpha:1];
    self.playButton=Button(@"Start sandbox",self,@selector(start));
    self.importButton=Button(@"About bundled artwork",self,@selector(artInfo));
    UIButton *help=Button(@"Controls and asset requirements",self,@selector(help));
    self.spinner=[[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleMedium];
    self.spinner.hidesWhenStopped=YES;
    UIStackView *buttons=[[UIStackView alloc] initWithArrangedSubviews:@[self.importButton,self.playButton]];
    buttons.axis=UILayoutConstraintAxisHorizontal; buttons.distribution=UIStackViewDistributionFillEqually; buttons.spacing=8;
    self.launcherStack=[[UIStackView alloc] initWithArrangedSubviews:@[title,subtitle,self.message,buttons,help,self.spinner]];
    self.launcherStack.axis=UILayoutConstraintAxisVertical; self.launcherStack.spacing=12;
    self.launcherStack.translatesAutoresizingMaskIntoConstraints=NO; [self.launcher addSubview:self.launcherStack];
    UILayoutGuide *safe=self.launcher.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [self.launcherStack.centerXAnchor constraintEqualToAnchor:safe.centerXAnchor],
        [self.launcherStack.centerYAnchor constraintEqualToAnchor:safe.centerYAnchor],
        [self.launcherStack.widthAnchor constraintLessThanOrEqualToConstant:680],
        [self.launcherStack.leadingAnchor constraintGreaterThanOrEqualToAnchor:safe.leadingAnchor constant:20],
        [self.launcherStack.trailingAnchor constraintLessThanOrEqualToAnchor:safe.trailingAnchor constant:-20],
        [self.launcherStack.topAnchor constraintGreaterThanOrEqualToAnchor:safe.topAnchor constant:8],
        [self.launcherStack.bottomAnchor constraintLessThanOrEqualToAnchor:safe.bottomAnchor constant:-8]
    ]];
    NSLayoutConstraint *width=[self.launcherStack.widthAnchor constraintEqualToAnchor:safe.widthAnchor constant:-40];
    width.priority=UILayoutPriorityDefaultHigh; width.active=YES;
}
- (void)showLauncher:(NSString *)message {
    [self.artDemo stop];
    [self.webGame stop];
    self.launcher.hidden=NO; self.gameTouch.hidden=YES; self.toolbar.hidden=YES; self.hint.hidden=YES;
    self.message.text=message; [self.spinner stopAnimating];
    self.importButton.enabled=!self.importing;
    self.playButton.enabled=!self.importing;
}
- (void)showLoading {
    [self showLauncher:@"Loading the original sprites and preparing both settlements. This happens off the UI thread."];
    [self.spinner startAnimating]; self.importButton.enabled=NO; self.playButton.enabled=NO;
}
- (void)showGame {
    self.launcher.hidden=YES;
    if (self.webGame.running) {
        self.gameTouch.hidden=YES; self.toolbar.hidden=YES; self.hint.hidden=YES;
        return;
    }
    self.gameTouch.hidden=self.artDemo.running; self.toolbar.hidden=NO; self.hint.hidden=NO;
    self.hint.text=self.artDemo.running ? @"Tap soldiers or buildings to select. Double-tap a soldier to select its type. Pinch or use +/− to zoom; MOVE opens the thumbstick." : @"Tap to select. Hold or use Order to move, gather, or attack. Two fingers pan.";
}
- (void)configurePopover:(UIAlertController *)alert {
    alert.popoverPresentationController.sourceView=self.toolbar;
    alert.popoverPresentationController.sourceRect=self.toolbar.bounds;
    alert.popoverPresentationController.permittedArrowDirections=UIPopoverArrowDirectionDown;
}
- (void)selectMode {
    if (self.artDemo.running) { [self.artDemo selectMode]; self.hint.text=@"Select: tap a soldier or building. Double-tap a soldier to select all of that type."; return; }
    OEInput_SetMode(OE_SELECT); self.hint.text=@"Select: tap a unit or drag a selection box. Hold for an order.";
}
- (void)orderMode {
    if (self.artDemo.running) { [self.artDemo orderMode]; self.hint.text=@"Order: select soldiers, tap terrain to move, or tap an enemy to attack."; return; }
    OEInput_SetMode(OE_COMMAND); self.hint.text=@"Order: tap terrain to move, a resource to gather, or an enemy to attack.";
}
- (void)panMode {
    if (self.artDemo.running) { [self.artDemo panMode]; self.hint.text=@"Pan: drag the camera. Pinch or use +/− to zoom."; return; }
    OEInput_SetMode(OE_PAN); self.hint.text=@"Pan: drag to move the camera. Select returns to unit selection.";
}
- (void)toggleMap {
    if (self.artDemo.running) { [self.artDemo toggleMap]; self.hint.text=@"Map: tap again to return to the angled camera."; return; }
    OEInput_ToggleMap();
}
- (void)start {
    if (self.importing) return;
    if (!self.webGame.running) {
        [self.artDemo stop];
        [self.webGame startInView:self.root.view];
    }
    [self showGame];
}
- (void)showActions {
    if (self.artDemo.running) { [self.artDemo showActionsFromViewController:self.root]; return; }
    if (!OEApp_HasGame() || self.root.presentedViewController) return;
    OEAction actions[OE_MAX_ACTIONS]; int count=OEApp_GetActions(actions,OE_MAX_ACTIONS);
    OEApp_Pause();
    UIAlertController *alert=[UIAlertController alertControllerWithTitle:@"Selected unit actions" message:count ? @"Choose an action, then tap its location on the map. Place trained units near their selected building." : @"Select a villager, town center, military unit, or production building first." preferredStyle:UIAlertControllerStyleActionSheet];
    for (int i=0;i<count;++i) {
        int index=actions[i].index;
        NSString *title=[NSString stringWithUTF8String:actions[i].title];
        [alert addAction:[UIAlertAction actionWithTitle:title style:UIAlertActionStyleDefault handler:^(UIAlertAction *a) { (void)a; OEApp_ChooseAction(index); }]];
    }
    [alert addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:^(UIAlertAction *a) { (void)a; OEApp_Resume(); }]];
    [self configurePopover:alert]; [self.root presentViewController:alert animated:YES completion:nil];
}
- (void)showPaused {
    if (self.artDemo.running) { [self.artDemo showMenuFromViewController:self.root]; return; }
    if (!OEApp_HasGame()) return;
    OEApp_Pause();
    if (self.root.presentedViewController) return;
    UIAlertController *alert=[UIAlertController alertControllerWithTitle:@"Sandbox paused" message:@"There is no strategic AI opponent in this port. Switch sides to control either settlement. Ending a game discards its state." preferredStyle:UIAlertControllerStyleActionSheet];
    [alert addAction:[UIAlertAction actionWithTitle:@"Resume" style:UIAlertActionStyleCancel handler:^(UIAlertAction *a) { (void)a; OEApp_Resume(); }]];
    [alert addAction:[UIAlertAction actionWithTitle:@"Center on town" style:UIAlertActionStyleDefault handler:^(UIAlertAction *a) { (void)a; OEApp_Home(); OEApp_Resume(); }]];
    [alert addAction:[UIAlertAction actionWithTitle:@"Switch Blue / Red" style:UIAlertActionStyleDefault handler:^(UIAlertAction *a) { (void)a; OEApp_Resume(); OEApp_SwitchPlayer(); }]];
    [alert addAction:[UIAlertAction actionWithTitle:@"End game" style:UIAlertActionStyleDestructive handler:^(UIAlertAction *a) { (void)a; OEApp_End(); }]];
    [self configurePopover:alert]; [self.root presentViewController:alert animated:YES completion:nil];
}
- (void)artInfo {
    if (self.root.presentedViewController) return;
    NSString *text=@"This sandbox bundles a selected set of 0 A.D. buildings, units, trees, and terrain textures. The artwork is from the 0 A.D. project and is available under CC BY-SA; the included attribution and license files are shipped with the app. No Age of Empires data or network connection is required for this scene.";
    UIAlertController *alert=[UIAlertController alertControllerWithTitle:@"Bundled 0 A.D. artwork" message:text preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleCancel handler:nil]];
    [self.root presentViewController:alert animated:YES completion:nil];
}
- (void)help {
    if (self.root.presentedViewController) return;
    NSString *text=@"This build bundles real 0 A.D. buildings, units, trees, and terrain textures. Tap a soldier or building to select it. Double-tap a soldier to select all friendly soldiers of that type. Use Order to tap terrain and move, tap an enemy to attack, or open MOVE for the analog thumbstick. Drag or use Pan to move the camera, and pinch or use +/− to zoom farther in. Actions builds a house, trains a hoplite, or plants an oak. Map switches to an overhead view.\n\nThe artwork attribution and CC BY-SA license are included in the app bundle. No Age of Empires data, importer, network multiplayer, campaign, strategic AI, audio, or save-to-disk is added.";
    UIAlertController *alert=[UIAlertController alertControllerWithTitle:@"OpenEmpire for iOS" message:text preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleCancel handler:nil]];
    [self.root presentViewController:alert animated:YES completion:nil];
}
- (void)importAssets {
    if (self.importing || OEApp_IsLoading() || self.root.presentedViewController) return;
    UIDocumentPickerViewController *picker=[[UIDocumentPickerViewController alloc] initForOpeningContentTypes:@[UTTypeFolder] asCopy:NO];
    picker.delegate=self; picker.allowsMultipleSelection=NO;
    [self.root presentViewController:picker animated:YES completion:nil];
}
- (void)documentPicker:(UIDocumentPickerViewController *)controller didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls {
    (void)controller;
    NSURL *source=urls.firstObject; if (!source) return;
    self.importing=YES; [self showLauncher:@"Copying and validating the selected Trial data..."]; [self.spinner startAnimating];
    NSURL *destination=self.dataURL;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
        @autoreleasepool {
            BOOL scoped=[source startAccessingSecurityScopedResource];
            NSFileManager *fm=[NSFileManager new];
            NSURL *parent=[destination URLByDeletingLastPathComponent];
            NSURL *staging=[parent URLByAppendingPathComponent:[@"Import-" stringByAppendingString:NSUUID.UUID.UUIDString] isDirectory:YES];
            __block NSError *failure=nil;
            [fm createDirectoryAtURL:staging withIntermediateDirectories:YES attributes:nil error:&failure];
            if (!failure) {
                NSFileCoordinator *coordinator=[[NSFileCoordinator alloc] initWithFilePresenter:nil];
                NSError *coordinationError=nil;
                [coordinator coordinateReadingItemAtURL:source options:0 error:&coordinationError byAccessor:^(NSURL *readURL) {
                    NSArray<NSURL *> *items=[fm contentsOfDirectoryAtURL:readURL includingPropertiesForKeys:@[NSURLIsRegularFileKey,NSURLIsSymbolicLinkKey,NSURLFileSizeKey] options:0 error:&failure];
                    for (unsigned i=0;i<OE_ASSET_COUNT && !failure;++i) {
                        NSString *name=[NSString stringWithUTF8String:OEAssetNames[i]];
                        NSURL *found=nil;
                        for (NSURL *item in items)
                            if ([item.lastPathComponent caseInsensitiveCompare:name]==NSOrderedSame) { found=item; break; }
                        NSNumber *regular=nil,*symlink=nil,*size=nil;
                        [found getResourceValue:&regular forKey:NSURLIsRegularFileKey error:nil];
                        [found getResourceValue:&symlink forKey:NSURLIsSymbolicLinkKey error:nil];
                        [found getResourceValue:&size forKey:NSURLFileSizeKey error:nil];
                        if (!found || !regular.boolValue || symlink.boolValue || size.unsignedLongLongValue>512ULL*1024*1024) {
                            failure=[NSError errorWithDomain:@"OpenEmpire" code:1 userInfo:@{NSLocalizedDescriptionKey:[NSString stringWithFormat:@"Missing or invalid %@. Choose the installed Trial's Data folder.",name]}]; break;
                        }
                        [fm copyItemAtURL:found toURL:[staging URLByAppendingPathComponent:name] error:&failure];
                    }
                }];
                if (!failure) failure=coordinationError;
            }
            char validation[512]={0};
            if (!failure && !OEAssets_CheckDirectory(staging.fileSystemRepresentation,validation,sizeof(validation)))
                failure=[NSError errorWithDomain:@"OpenEmpire" code:2 userInfo:@{NSLocalizedDescriptionKey:[NSString stringWithUTF8String:validation]}];
            /* A failed import must not destroy an existing playable dataset. */
            if (!failure) {
                NSURL *backup=[parent URLByAppendingPathComponent:[@"Backup-" stringByAppendingString:NSUUID.UUID.UUIDString] isDirectory:YES];
                BOOL hadPrevious=[fm fileExistsAtPath:destination.path];
                if (hadPrevious) [fm moveItemAtURL:destination toURL:backup error:&failure];
                if (!failure && ![fm moveItemAtURL:staging toURL:destination error:&failure]) {
                    if (hadPrevious) [fm moveItemAtURL:backup toURL:destination error:nil];
                } else if (!failure && hadPrevious) [fm removeItemAtURL:backup error:nil];
                if (!failure) [destination setResourceValue:@YES forKey:NSURLIsExcludedFromBackupKey error:nil];
            }
            [fm removeItemAtURL:staging error:nil];
            if (scoped) [source stopAccessingSecurityScopedResource];
            NSString *result=failure ? failure.localizedDescription : @"Assets imported. Start a two-settlement sandbox. Each side begins with 750 of each resource.";
            dispatch_async(dispatch_get_main_queue(),^{ self.importing=NO; [self showLauncher:result]; });
        }
    });
}
- (void)willResign:(NSNotification *)notification {
    (void)notification;
    if (self.webGame.running) [self.webGame setActive:NO];
    else if (self.artDemo.running) [self.artDemo setActive:NO];
    else OEApp_SetActive(false);
}
- (void)didBecome:(NSNotification *)notification {
    (void)notification;
    if (self.webGame.running) [self.webGame setActive:YES];
    else if (self.artDemo.running) [self.artDemo setActive:YES];
    else OEApp_SetActive(true);
}
@end

void OEPlatform_Install(SDL_Window *window) {
    platform=[[OEPlatformController alloc] initWithWindow:window];
    if (!platform) { SDL_LogCritical(SDL_LOG_CATEGORY_APPLICATION,"Could not attach UIKit controls"); abort(); }
}
void OEPlatform_ShowLauncher(const char *message) { [platform showLauncher:message ? [NSString stringWithUTF8String:message] : @""]; }
void OEPlatform_ShowLoading(void) { [platform showLoading]; }
void OEPlatform_ShowGame(void) { [platform showGame]; }
void OEPlatform_ShowPaused(void) { [platform showPaused]; }
void OEPlatform_SetHint(const char *message) { platform.hint.text=message ? [NSString stringWithUTF8String:message] : @""; }
