/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Native entry for the Medieval Ages web game.
   Apps linked against the iOS 27 SDK must adopt the UIScene lifecycle or UIKit traps at launch
   (UIApplicationEvaluateRuntimeIssueForNoSceneLifecycleAdoption). SDL2's UIKit backend only knows
   the legacy app-delegate window, so the shipped target no longer boots through SDL_UIKitRunApp:
   the web game needs nothing from SDL but a view to live in, so a scene delegate hosts OEWebGame
   directly. The SDL engine and OEPlatform remain in the target, unused, for the original port. */
#import <UIKit/UIKit.h>
#import "OEWebGame.h"

@interface OEGameViewController : UIViewController
@property(nonatomic,strong) OEWebGame *webGame;
@end

@implementation OEGameViewController
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor=UIColor.blackColor;
    self.overrideUserInterfaceStyle=UIUserInterfaceStyleDark;
    self.webGame=[OEWebGame new];
    [self.webGame startInView:self.view];
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
