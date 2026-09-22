/* SPDX-License-Identifier: GPL-3.0-or-later */
#import <UIKit/UIKit.h>

@interface OEArtDemo : NSObject
@property(nonatomic, readonly, getter=isRunning) BOOL running;
@property(nonatomic, copy) void (^onEnd)(void);

- (void)startInView:(UIView *)host presentingController:(UIViewController *)controller;
- (void)stop;
- (void)setActive:(BOOL)active;
- (void)selectMode;
- (void)orderMode;
- (void)panMode;
- (void)toggleMap;
- (void)showActionsFromViewController:(UIViewController *)controller;
- (void)showMenuFromViewController:(UIViewController *)controller;
@end
