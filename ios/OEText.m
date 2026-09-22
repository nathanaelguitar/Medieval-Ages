/* SPDX-License-Identifier: GPL-3.0-or-later */
#import <UIKit/UIKit.h>
#define Point OEPoint
#include "Text.h"
#undef Point
#include <stdarg.h>
#include <stdio.h>
#include <math.h>
#include <stdlib.h>

@interface OETextEntry : NSObject
@property(nonatomic) SDL_Texture *texture;
@property(nonatomic) int width;
@property(nonatomic) int height;
@property(nonatomic,copy) NSString *key;
@end
@implementation OETextEntry
- (void)dealloc { if (_texture) SDL_DestroyTexture(_texture); }
@end
static NSMutableArray<OETextEntry *> *textCache;

Text Text_Build(const char *path, int32_t size, uint32_t color) {
    (void)path; (void)color;
    Text text = {0}; text.point_size = size;
    text.color = (SDL_Color){235,240,246,255};
    return text;
}
static OETextEntry *TextureForText(Text text, SDL_Renderer *renderer, NSString *string) {
    if (!textCache) textCache = [NSMutableArray array];
    NSString *key = [NSString stringWithFormat:@"%p:%d:%@",(void *)renderer,text.point_size,string];
    for (NSUInteger i=0;i<textCache.count;++i) {
        OETextEntry *entry=textCache[i];
        if ([entry.key isEqualToString:key]) {
            [textCache removeObjectAtIndex:i]; [textCache addObject:entry]; return entry;
        }
    }
    UIFont *font=[UIFont monospacedSystemFontOfSize:text.point_size weight:UIFontWeightRegular];
    NSDictionary *attributes=@{NSFontAttributeName:font, NSForegroundColorAttributeName:[UIColor colorWithRed:text.color.r/255.0 green:text.color.g/255.0 blue:text.color.b/255.0 alpha:1]};
    CGSize measured=[string sizeWithAttributes:attributes];
    int w=MAX(1,MIN(4096,(int)ceil(measured.width)+2));
    int h=MAX(1,MIN(256,(int)ceil(font.lineHeight)+2));
    uint8_t *pixels=calloc((size_t)w*h,4);
    if (!pixels) return nil;
    CGColorSpaceRef colorSpace=CGColorSpaceCreateDeviceRGB();
    CGContextRef context=CGBitmapContextCreate(pixels,w,h,8,(size_t)w*4,colorSpace,kCGImageAlphaPremultipliedLast|kCGBitmapByteOrder32Big);
    CGColorSpaceRelease(colorSpace);
    if (!context) { free(pixels); return nil; }
    CGContextTranslateCTM(context,0,h); CGContextScaleCTM(context,1,-1);
    UIGraphicsPushContext(context); [string drawAtPoint:CGPointZero withAttributes:attributes]; UIGraphicsPopContext();
    CGContextRelease(context);
    /* SDL alpha blending expects straight rather than premultiplied RGB. */
    for (size_t i=0;i<(size_t)w*h;++i) {
        unsigned a=pixels[i*4+3];
        if (a && a<255)
            for (int channel=0;channel<3;++channel)
                pixels[i*4+channel]=(uint8_t)MIN(255u,(unsigned)pixels[i*4+channel]*255u/a);
    }
    SDL_Surface *surface=SDL_CreateRGBSurfaceWithFormatFrom(pixels,w,h,32,w*4,SDL_PIXELFORMAT_RGBA32);
    SDL_Texture *texture=surface ? SDL_CreateTextureFromSurface(renderer,surface) : NULL;
    if (surface) SDL_FreeSurface(surface);
    free(pixels);
    if (!texture) return nil;
    SDL_SetTextureBlendMode(texture,SDL_BLENDMODE_BLEND);
    OETextEntry *entry=[OETextEntry new]; entry.key=key; entry.texture=texture; entry.width=w; entry.height=h;
    if (textCache.count>=128) [textCache removeObjectAtIndex:0];
    [textCache addObject:entry];
    return entry;
}
int32_t Text_Puts(Text text, SDL_Renderer *renderer, OEPoint point, Position position, int32_t alpha, int32_t line, const char *value) {
    if (!value || !renderer) return 0;
    @autoreleasepool {
        NSString *string=[NSString stringWithUTF8String:value];
        if (!string) return 0;
        NSArray<NSString *> *lines=[string componentsSeparatedByString:@"\n"];
        int row=0;
        for (NSString *part in lines) {
            OETextEntry *entry=TextureForText(text,renderer,part);
            if (!entry) { ++row; continue; }
            SDL_Rect rect={point.x,point.y+(line+row)*entry.height,entry.width,entry.height};
            switch(position) {
                case POSITION_TOP_LEFT: break;
                case POSITION_TOP_RITE: rect.x-=rect.w; break;
                case POSITION_BOT_LEFT: rect.y-=rect.h; break;
                case POSITION_BOT_RITE: rect.x-=rect.w; rect.y-=rect.h; break;
                case POSITION_MIDDLE: rect.x-=rect.w/2; rect.y-=rect.h/2; break;
            }
            SDL_SetTextureAlphaMod(entry.texture,(uint8_t)MAX(0,MIN(255,alpha)));
            SDL_RenderCopy(renderer,entry.texture,NULL,&rect);
            ++row;
        }
        return row;
    }
}
int32_t Text_Printf(Text text, SDL_Renderer *renderer, OEPoint point, Position position, int32_t alpha, int32_t line, const char *format, ...) {
    if (!format) return 0;
    va_list args; va_start(args,format);
    va_list copy; va_copy(copy,args); int length=vsnprintf(NULL,0,format,copy); va_end(copy);
    if (length<0 || length>65536) { va_end(args); return 0; }
    char *buffer=malloc((size_t)length+1);
    if (!buffer) { va_end(args); return 0; }
    vsnprintf(buffer,(size_t)length+1,format,args); va_end(args);
    int lines=Text_Puts(text,renderer,point,position,alpha,line,buffer);
    free(buffer); return lines;
}
void Text_Free(Text text) { (void)text; [textCache removeAllObjects]; }
