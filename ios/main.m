/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Native entry for the Medieval Ages web game.
   Apps linked against the iOS 27 SDK must adopt the UIScene lifecycle or UIKit traps at launch
   (UIApplicationEvaluateRuntimeIssueForNoSceneLifecycleAdoption). SDL2's UIKit backend only knows
   the legacy app-delegate window, so the shipped target no longer boots through SDL_UIKitRunApp:
   the web game needs nothing from SDL but a view to live in, so a scene delegate hosts OEWebGame
   directly. The SDL engine and OEPlatform remain in the target, unused, for the original port. */
#import <UIKit/UIKit.h>
#import <AVFoundation/AVFoundation.h>
#import "OEWebGame.h"

@interface OEGameViewController : UIViewController
@property(nonatomic,strong) OEWebGame *webGame;
@property(nonatomic,strong) UIView *introView;
@property(nonatomic,strong) AVPlayer *introPlayer;
@property(nonatomic,strong) AVPlayerLayer *introLayer;
- (void)resumeIntro;
@end

@implementation OEGameViewController
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor=UIColor.blackColor;
    self.overrideUserInterfaceStyle=UIUserInterfaceStyleDark;
    self.webGame=[OEWebGame new];
    [self.webGame startInView:self.view];
    [self playIntro];
}
/* The intro film plays natively over the web view. WebKit refuses to autoplay video while the
   phone is in Low Power Mode (NotAllowedError even when muted), which silently skipped the
   film; AVPlayer has no such rule. Watching it through once is required; afterwards a Skip
   button sits bottom right. */
- (void)playIntro {
    NSURL *url=[NSBundle.mainBundle URLForResource:@"intro" withExtension:@"mp4" subdirectory:@"open-empire-mobile"];
    if (!url) return;
    [AVAudioSession.sharedInstance setCategory:AVAudioSessionCategoryPlayback mode:AVAudioSessionModeDefault
                                       options:AVAudioSessionCategoryOptionMixWithOthers error:nil];
    [AVAudioSession.sharedInstance setActive:YES error:nil];
    UIView *v=[[UIView alloc] initWithFrame:self.view.bounds];
    v.autoresizingMask=UIViewAutoresizingFlexibleWidth|UIViewAutoresizingFlexibleHeight;
    v.backgroundColor=UIColor.blackColor;
    self.introPlayer=[AVPlayer playerWithURL:url];
    self.introLayer=[AVPlayerLayer playerLayerWithPlayer:self.introPlayer];
    self.introLayer.videoGravity=AVLayerVideoGravityResizeAspect;
    self.introLayer.frame=v.bounds;
    [v.layer addSublayer:self.introLayer];
    if ([NSUserDefaults.standardUserDefaults boolForKey:@"pe_intro_seen"]) {
        UIButton *skip=[UIButton buttonWithType:UIButtonTypeCustom];
        [skip setTitle:@"Skip \u25B6" forState:UIControlStateNormal];
        [skip setTitleColor:[UIColor colorWithRed:0.89 green:0.76 blue:0.48 alpha:1] forState:UIControlStateNormal];
        skip.titleLabel.font=[UIFont fontWithName:@"Palatino-Bold" size:15]?:[UIFont boldSystemFontOfSize:15];
        skip.backgroundColor=[UIColor colorWithWhite:0 alpha:0.45];
        skip.layer.cornerRadius=18;
        skip.layer.borderWidth=1;
        skip.layer.borderColor=[UIColor colorWithRed:0.89 green:0.76 blue:0.48 alpha:0.6].CGColor;
        skip.contentEdgeInsets=UIEdgeInsetsMake(8,18,8,18);
        skip.translatesAutoresizingMaskIntoConstraints=NO;
        [skip addTarget:self action:@selector(skipIntro) forControlEvents:UIControlEventTouchUpInside];
        [v addSubview:skip];
        [NSLayoutConstraint activateConstraints:@[
            [skip.trailingAnchor constraintEqualToAnchor:v.safeAreaLayoutGuide.trailingAnchor constant:-18],
            [skip.bottomAnchor constraintEqualToAnchor:v.safeAreaLayoutGuide.bottomAnchor constant:-14]]];
    }
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(introEnded:)
                                               name:AVPlayerItemDidPlayToEndTimeNotification object:self.introPlayer.currentItem];
    [self.view addSubview:v];
    self.introView=v;
    [self.introPlayer play];
}
- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    if (self.introView) self.introLayer.frame=self.introView.bounds;
}
- (void)introEnded:(NSNotification *)note { (void)note; [self finishIntro:YES]; }
- (void)skipIntro { [self finishIntro:NO]; }
- (void)resumeIntro { if (self.introView && self.introPlayer.rate==0) [self.introPlayer play]; }
- (void)finishIntro:(BOOL)watched {
    if (!self.introView) return;
    if (watched) [NSUserDefaults.standardUserDefaults setBool:YES forKey:@"pe_intro_seen"];
    [NSNotificationCenter.defaultCenter removeObserver:self name:AVPlayerItemDidPlayToEndTimeNotification object:nil];
    [self.introPlayer pause];
    UIView *v=self.introView;
    self.introView=nil;
    [UIView animateWithDuration:0.8 animations:^{ v.alpha=0; } completion:^(BOOL done) {
        (void)done; [v removeFromSuperview]; self.introPlayer=nil; self.introLayer=nil;
    }];
}
- (BOOL)prefersStatusBarHidden { return YES; }
- (BOOL)prefersHomeIndicatorAutoHidden { return YES; }
/* Keep the first swipe from the bottom edge as a game drag rather than leaving the app. */
- (UIRectEdge)preferredScreenEdgesDeferringSystemGestures { return UIRectEdgeBottom; }
- (UIInterfaceOrientationMask)supportedInterfaceOrientations { return UIInterfaceOrientationMaskLandscape; }
@end

@interface OESceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic,strong) UIWindow *window;
@end

@implementation OESceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    (void)session; (void)options;
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window=[[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.window.rootViewController=[OEGameViewController new];
    [self.window makeKeyAndVisible];
}
- (void)sceneDidBecomeActive:(UIScene *)scene {
    (void)scene;
    [((OEGameViewController *)self.window.rootViewController).webGame setActive:YES];
    [(OEGameViewController *)self.window.rootViewController resumeIntro];
    /* A match is played hands-off for long stretches (watching villagers work), so the screen
       must not auto-lock under it -- Low Power Mode cuts auto-lock to 30 s. */
    UIApplication.sharedApplication.idleTimerDisabled=YES;
}
- (void)sceneWillResignActive:(UIScene *)scene {
    (void)scene;
    [((OEGameViewController *)self.window.rootViewController).webGame setActive:NO];
    UIApplication.sharedApplication.idleTimerDisabled=NO;
}
@end

@interface OEAppDelegate : UIResponder <UIApplicationDelegate>
@end

@implementation OEAppDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    (void)application; (void)options;
    return YES;
}
- (UISceneConfiguration *)application:(UIApplication *)application configurationForConnectingSceneSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    (void)application; (void)options;
    UISceneConfiguration *config=[[UISceneConfiguration alloc] initWithName:@"Default" sessionRole:session.role];
    config.delegateClass=OESceneDelegate.class;
    return config;
}
@end

int main(int argc, char **argv) {
    @autoreleasepool {
        return UIApplicationMain(argc,argv,nil,NSStringFromClass(OEAppDelegate.class));
    }
}
