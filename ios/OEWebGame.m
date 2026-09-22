/* SPDX-License-Identifier: GPL-3.0-or-later */
#import "OEWebGame.h"
#import <WebKit/WebKit.h>

@interface OEWebGame () <WKNavigationDelegate>
@property(nonatomic,readwrite,getter=isRunning) BOOL running;
@property(nonatomic,strong) WKWebView *webView;
@end

@implementation OEWebGame

- (void)webView:(WKWebView *)webView didFinishNavigation:(WKNavigation *)navigation {
    (void)navigation;
    [webView evaluateJavaScript:@"JSON.stringify((()=>{const c=document.querySelector('canvas');return {title:document.title,canvas:!!c,width:c?.width||0,height:c?.height||0}})())"
               completionHandler:^(id result, NSError *error) {
        if (error) NSLog(@"OpenEmpire Mobile: page validation failed: %@",error.localizedDescription);
        else NSLog(@"OpenEmpire Mobile: page loaded %@",result);
    }];
}

- (void)webView:(WKWebView *)webView didFailNavigation:(WKNavigation *)navigation withError:(NSError *)error {
    (void)webView; (void)navigation;
    NSLog(@"OpenEmpire Mobile: navigation failed: %@",error.localizedDescription);
}

- (void)webView:(WKWebView *)webView didFailProvisionalNavigation:(WKNavigation *)navigation withError:(NSError *)error {
    (void)webView; (void)navigation;
    NSLog(@"OpenEmpire Mobile: provisional navigation failed: %@",error.localizedDescription);
}

- (void)startInView:(UIView *)host {
    if (self.running || !host) return;

    WKWebViewConfiguration *configuration=[WKWebViewConfiguration new];
    configuration.allowsInlineMediaPlayback=YES;
    if (@available(iOS 10.0,*))
        configuration.mediaTypesRequiringUserActionForPlayback=WKAudiovisualMediaTypeNone;

    self.webView=[[WKWebView alloc] initWithFrame:host.bounds configuration:configuration];
    self.webView.autoresizingMask=UIViewAutoresizingFlexibleWidth|UIViewAutoresizingFlexibleHeight;
    self.webView.opaque=NO;
    self.webView.backgroundColor=UIColor.blackColor;
    self.webView.scrollView.scrollEnabled=NO;
    self.webView.scrollView.contentInsetAdjustmentBehavior=UIScrollViewContentInsetAdjustmentNever;
    self.webView.allowsBackForwardNavigationGestures=NO;
    self.webView.navigationDelegate=self;
    [host insertSubview:self.webView atIndex:0];

    NSURL *url=[[NSBundle mainBundle] URLForResource:@"index" withExtension:@"html" subdirectory:@"open-empire-mobile"];
    if (url) {
        [self.webView loadFileURL:url allowingReadAccessToURL:url.URLByDeletingLastPathComponent];
    } else {
        NSString *html=@"<html><body style='background:#111;color:white;font:17px -apple-system;text-align:center;padding:40px'>Open Empire Mobile is missing its bundled index.html.</body></html>";
        [self.webView loadHTMLString:html baseURL:nil];
    }
    self.running=YES;
}

- (void)stop {
    if (!self.running) return;
    self.webView.navigationDelegate=nil;
    [self.webView stopLoading];
    [self.webView removeFromSuperview];
    self.webView=nil;
    self.running=NO;
}

- (void)setActive:(BOOL)active {
    if (!self.running) return;
    if (active) [self.webView setNeedsLayout];
}

@end
