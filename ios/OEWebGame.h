/* SPDX-License-Identifier: GPL-3.0-or-later */
#import <UIKit/UIKit.h>

@interface OEWebGame : NSObject
@property(nonatomic,readonly,getter=isRunning) BOOL running;
- (void)startInView:(UIView *)host;
- (void)stop;
- (void)setActive:(BOOL)active;
@end
