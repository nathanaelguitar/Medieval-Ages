/* SPDX-License-Identifier: GPL-3.0-or-later */
#import "OEArtDemo.h"
#import <SceneKit/SceneKit.h>
#import <QuartzCore/QuartzCore.h>
#import <math.h>

typedef NS_ENUM(NSInteger, OEArtMode) {
    OEArtModeSelect,
    OEArtModeOrder,
    OEArtModePan
};

static NSString *ArtPath(NSString *relativePath) {
    return [[NSBundle mainBundle] pathForResource:[NSString stringWithFormat:@"ZeroADArt/%@", relativePath]
                                             ofType:nil];
}

static UIImage *ArtImage(NSString *relativePath) {
    NSString *path=ArtPath(relativePath);
    return path ? [UIImage imageWithContentsOfFile:path] : nil;
}

static NSValue *NodeKey(SCNNode *node) {
    return [NSValue valueWithPointer:(__bridge const void *)node];
}

@interface OEThumbstickView : UIView
@property(nonatomic,copy) void (^onValueChanged)(CGPoint value);
@property(nonatomic,copy) void (^onEnded)(void);
@property(nonatomic,readonly) CGPoint value;
@end

@implementation OEThumbstickView {
    CGPoint _knobCenter;
    BOOL _tracking;
}

- (instancetype)initWithFrame:(CGRect)frame {
    if ((self=[super initWithFrame:frame])) {
        self.backgroundColor=UIColor.clearColor;
        self.multipleTouchEnabled=NO;
        self.accessibilityLabel=@"Unit movement thumbstick";
        _knobCenter=CGPointMake(CGRectGetMidX(frame),CGRectGetMidY(frame));
    }
    return self;
}

- (void)layoutSubviews {
    [super layoutSubviews];
    if (!_tracking) _knobCenter=CGPointMake(CGRectGetMidX(self.bounds),CGRectGetMidY(self.bounds));
    [self setNeedsDisplay];
}

- (void)drawRect:(CGRect)rect {
    (void)rect;
    CGContextRef context=UIGraphicsGetCurrentContext();
    CGPoint center=CGPointMake(CGRectGetMidX(self.bounds),CGRectGetMidY(self.bounds));
    CGFloat radius=MIN(CGRectGetWidth(self.bounds),CGRectGetHeight(self.bounds))*0.5-9;
    CGContextSetShadowWithColor(context,CGSizeMake(0,3),8,[UIColor colorWithWhite:0 alpha:0.35].CGColor);
    [[UIColor colorWithWhite:0.03 alpha:0.80] setFill];
    [[UIColor colorWithWhite:1 alpha:0.24] setStroke];
    UIBezierPath *base=[UIBezierPath bezierPathWithArcCenter:center radius:radius startAngle:0 endAngle:(CGFloat)(M_PI*2) clockwise:YES];
    base.lineWidth=1.0;
    [base fill]; [base stroke];

    [[UIColor colorWithWhite:1 alpha:0.12] setStroke];
    UIBezierPath *inner=[UIBezierPath bezierPathWithArcCenter:center radius:radius*0.55 startAngle:0 endAngle:(CGFloat)(M_PI*2) clockwise:YES];
    inner.lineWidth=1.0;
    [inner stroke];

    CGFloat knobRadius=27;
    CGContextSetShadowWithColor(context,CGSizeMake(0,2),5,[UIColor colorWithWhite:0 alpha:0.45].CGColor);
    [[UIColor colorWithRed:0.16 green:0.43 blue:0.62 alpha:0.98] setFill];
    [[UIColor colorWithWhite:1 alpha:0.40] setStroke];
    UIBezierPath *knob=[UIBezierPath bezierPathWithArcCenter:_knobCenter radius:knobRadius startAngle:0 endAngle:(CGFloat)(M_PI*2) clockwise:YES];
    knob.lineWidth=1.0;
    [knob fill]; [knob stroke];
}

- (void)updateWithPoint:(CGPoint)point {
    CGPoint center=CGPointMake(CGRectGetMidX(self.bounds),CGRectGetMidY(self.bounds));
    CGFloat radius=MIN(CGRectGetWidth(self.bounds),CGRectGetHeight(self.bounds))*0.5-36;
    CGFloat dx=point.x-center.x;
    CGFloat dy=point.y-center.y;
    CGFloat distance=hypot(dx,dy);
    if (distance>radius && distance>0) {
        CGFloat factor=radius/distance;
        dx*=factor; dy*=factor;
    }
    _knobCenter=CGPointMake(center.x+dx,center.y+dy);
    _value=CGPointMake(radius>0 ? dx/radius : 0,radius>0 ? dy/radius : 0);
    [self setNeedsDisplay];
    if (self.onValueChanged) self.onValueChanged(_value);
}

- (void)reset {
    _tracking=NO;
    _knobCenter=CGPointMake(CGRectGetMidX(self.bounds),CGRectGetMidY(self.bounds));
    _value=CGPointZero;
    [self setNeedsDisplay];
    if (self.onEnded) self.onEnded();
}

- (void)touchesBegan:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    (void)event;
    UITouch *touch=touches.anyObject;
    if (!touch || _tracking) return;
    _tracking=YES;
    [self updateWithPoint:[touch locationInView:self]];
}

- (void)touchesMoved:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    (void)event;
    UITouch *touch=touches.anyObject;
    if (_tracking && touch) [self updateWithPoint:[touch locationInView:self]];
}

- (void)touchesEnded:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    (void)touches; (void)event;
    if (_tracking) [self reset];
}

- (void)touchesCancelled:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    (void)touches; (void)event;
    if (_tracking) [self reset];
}

@end

@interface OEArtDemo () <SCNSceneRendererDelegate>
@property(nonatomic, readwrite, getter=isRunning) BOOL running;
@property(nonatomic,strong) SCNView *sceneView;
@property(nonatomic,strong) SCNScene *scene;
@property(nonatomic,strong) SCNNode *world;
@property(nonatomic,strong) SCNNode *ground;
@property(nonatomic,strong) SCNNode *cameraNode;
@property(nonatomic,strong) SCNNode *selectedUnit;
@property(nonatomic,strong) SCNNode *selectedBuilding;
@property(nonatomic,strong) SCNNode *selectionRing;
@property(nonatomic,strong) NSMutableArray<SCNNode *> *units;
@property(nonatomic,strong) NSMutableArray<SCNNode *> *buildings;
@property(nonatomic,strong) NSMutableArray<SCNNode *> *selectedUnits;
@property(nonatomic,strong) NSMutableArray<SCNNode *> *selectionRings;
@property(nonatomic,strong) UILabel *statusLabel;
@property(nonatomic,strong) UIView *movePad;
@property(nonatomic,strong) OEThumbstickView *moveStick;
@property(nonatomic,strong) CADisplayLink *moveStickDisplayLink;
@property(nonatomic,strong) UIButton *movePadToggle;
@property(nonatomic,strong) UIButton *zoomInButton;
@property(nonatomic,strong) UIButton *zoomOutButton;
@property(nonatomic,strong) NSMutableDictionary<NSValue *,NSNumber *> *hitPoints;
@property(nonatomic,strong) NSMutableDictionary<NSValue *,SCNNode *> *attackTargets;
@property(nonatomic,strong) NSMutableDictionary<NSValue *,NSNumber *> *nextAttackTimes;
@property(nonatomic,strong) SCNNode *focusedAttackTarget;
@property(nonatomic,weak) UIViewController *presentingController;
@property(nonatomic) OEArtMode mode;
@property(nonatomic) BOOL mapVisible;
@property(nonatomic) BOOL blueSideActive;
@property(nonatomic) NSUInteger buildingCount;
@property(nonatomic) NSUInteger unitCount;
@end

@implementation OEArtDemo

- (instancetype)init {
    if ((self=[super init])) {
        _units=[NSMutableArray array];
        _buildings=[NSMutableArray array];
        _selectedUnits=[NSMutableArray array];
        _selectionRings=[NSMutableArray array];
        _hitPoints=[NSMutableDictionary dictionary];
        _attackTargets=[NSMutableDictionary dictionary];
        _nextAttackTimes=[NSMutableDictionary dictionary];
        _mode=OEArtModeSelect;
        _blueSideActive=YES;
    }
    return self;
}

- (void)startInView:(UIView *)host presentingController:(UIViewController *)controller {
    if (self.running || !host) return;
    self.presentingController=controller;
    self.sceneView=[[SCNView alloc] initWithFrame:host.bounds];
    self.sceneView.autoresizingMask=UIViewAutoresizingFlexibleWidth|UIViewAutoresizingFlexibleHeight;
    self.sceneView.backgroundColor=[UIColor colorWithRed:0.035 green:0.055 blue:0.08 alpha:1];
    self.sceneView.antialiasingMode=SCNAntialiasingModeMultisampling4X;
    self.sceneView.autoenablesDefaultLighting=NO;
    self.sceneView.allowsCameraControl=NO;
    self.sceneView.rendersContinuously=YES;
    [host insertSubview:self.sceneView atIndex:0];

    self.running=YES;
    self.mapVisible=NO;
    self.buildingCount=0;
    self.unitCount=0;
    [self.units removeAllObjects];
    [self.buildings removeAllObjects];
    [self.selectedUnits removeAllObjects];
    [self.selectionRings removeAllObjects];
    [self.hitPoints removeAllObjects];
    [self.attackTargets removeAllObjects];
    [self.nextAttackTimes removeAllObjects];
    self.focusedAttackTarget=nil;
    [self buildScene];
    [self installGestures];
    [self installControls];
    self.sceneView.playing=YES;
}

- (void)stop {
    if (!self.running) return;
    self.sceneView.playing=NO;
    [self.moveStickDisplayLink invalidate];
    self.moveStickDisplayLink=nil;
    self.sceneView.delegate=nil;
    [self.sceneView removeFromSuperview];
    self.sceneView=nil;
    self.scene=nil;
    self.world=nil;
    self.ground=nil;
    self.cameraNode=nil;
    self.selectedUnit=nil;
    self.selectedBuilding=nil;
    self.selectionRing=nil;
    [self.units removeAllObjects];
    [self.buildings removeAllObjects];
    [self.selectedUnits removeAllObjects];
    [self.selectionRings removeAllObjects];
    [self.hitPoints removeAllObjects];
    [self.attackTargets removeAllObjects];
    [self.nextAttackTimes removeAllObjects];
    self.focusedAttackTarget=nil;
    self.statusLabel=nil;
    self.movePad=nil;
    self.moveStick=nil;
    self.movePadToggle=nil;
    self.zoomInButton=nil;
    self.zoomOutButton=nil;
    self.running=NO;
}

- (void)setActive:(BOOL)active {
    if (self.running) self.sceneView.playing=active;
}

- (void)buildScene {
    self.scene=[SCNScene scene];
    self.scene.background.contents=[UIColor colorWithRed:0.035 green:0.055 blue:0.08 alpha:1];
    self.sceneView.scene=self.scene;
    self.sceneView.delegate=self;

    self.world=[SCNNode node];
    [self.scene.rootNode addChildNode:self.world];
    [self addGround];
    [self addLighting];
    [self addSettlements];
    [self addNature];
    [self addStartingUnits];
    [self addCamera];
    [self addStatusOverlay];
}

- (void)addGround {
    SCNPlane *plane=[SCNPlane planeWithWidth:72 height:72];
    SCNMaterial *material=[SCNMaterial material];
    UIImage *image=ArtImage(@"textures/terrain/types/aegean_anatolia/dirt_01.png");
    material.diffuse.contents=image ?: [UIColor colorWithRed:0.22 green:0.17 blue:0.11 alpha:1];
    material.diffuse.wrapS=SCNWrapModeRepeat;
    material.diffuse.wrapT=SCNWrapModeRepeat;
    material.diffuse.contentsTransform=SCNMatrix4MakeScale(14,14,1);
    material.lightingModelName=SCNLightingModelLambert;
    plane.firstMaterial=material;
    self.ground=[SCNNode nodeWithGeometry:plane];
    self.ground.name=@"ground";
    self.ground.eulerAngles=SCNVector3Make((float)-M_PI_2,0,0);
    self.ground.position=SCNVector3Make(0,-0.04,0);
    [self.world addChildNode:self.ground];
}

- (void)addLighting {
    SCNLight *ambient=[SCNLight light];
    ambient.type=SCNLightTypeAmbient;
    ambient.color=[UIColor colorWithWhite:0.72 alpha:1];
    ambient.intensity=650;
    SCNNode *ambientNode=[SCNNode node]; ambientNode.light=ambient;
    [self.scene.rootNode addChildNode:ambientNode];

    SCNLight *sun=[SCNLight light];
    sun.type=SCNLightTypeDirectional;
    sun.color=[UIColor colorWithRed:1 green:0.91 blue:0.72 alpha:1];
    sun.intensity=1050;
    sun.castsShadow=YES;
    sun.shadowMode=SCNShadowModeDeferred;
    sun.shadowRadius=3;
    SCNNode *sunNode=[SCNNode node]; sunNode.light=sun;
    sunNode.position=SCNVector3Make(-12,20,8);
    sunNode.eulerAngles=SCNVector3Make((float)(-M_PI/3.0),(float)(-M_PI/6.0),0);
    [self.scene.rootNode addChildNode:sunNode];
}

- (void)addSettlements {
    [self addBuilding:@"converted/structural/athen_cc_struct.obj"
              texture:@"textures/skins/structural/hele_struct.png"
                target:5.2 position:SCNVector3Make(-10,0,-3) tint:nil];
    [self addBuilding:@"converted/structural/athen_barracks_struct.obj"
              texture:@"textures/skins/structural/hele_struct.png"
                target:3.1 position:SCNVector3Make(-6.2,0,-4.1) tint:nil];
    [self addBuilding:@"converted/props/hele_house_a_struct.obj"
              texture:@"textures/skins/structural/hele_struct.png"
                target:2.4 position:SCNVector3Make(-7.8,0,1.8) tint:nil];

    [self addBuilding:@"converted/structural/hele_fortress_up.obj"
              texture:@"textures/skins/structural/hele_struct.png"
                target:5.0 position:SCNVector3Make(10,0,-3) tint:nil];
    [self addBuilding:@"converted/structural/athen_barracks_struct.obj"
              texture:@"textures/skins/structural/hele_struct_b.png"
                target:3.1 position:SCNVector3Make(6.2,0,-4.1) tint:nil];
    [self addBuilding:@"converted/props/hele_house_a_struct.obj"
              texture:@"textures/skins/structural/hele_struct_b.png"
                target:2.4 position:SCNVector3Make(7.8,0,1.8) tint:nil];

    [self addSettlementMarkerAt:SCNVector3Make(-10,4.1,-3)
                           title:@"BLUE SETTLEMENT"
                           color:[UIColor colorWithRed:0.2 green:0.55 blue:1 alpha:1]];
    [self addSettlementMarkerAt:SCNVector3Make(10,3.9,-3)
                           title:@"RED SETTLEMENT"
                           color:[UIColor colorWithRed:1 green:0.27 blue:0.25 alpha:1]];
}

- (void)addNature {
    NSArray<NSValue *> *oakPositions=@[
        [NSValue valueWithSCNVector3:SCNVector3Make(-11,0,-8)],
        [NSValue valueWithSCNVector3:SCNVector3Make(-9,0,6)],
        [NSValue valueWithSCNVector3:SCNVector3Make(-1,0,7)],
        [NSValue valueWithSCNVector3:SCNVector3Make(10,0,6)],
        [NSValue valueWithSCNVector3:SCNVector3Make(11,0,-8)],
        [NSValue valueWithSCNVector3:SCNVector3Make(1,0,-8)]
    ];
    for (NSValue *value in oakPositions)
        [self addModel:@"converted/gaia/oak_tree_a.obj"
                texture:@"textures/skins/gaia/oak_tree_a.png"
                  target:3.9 position:value.SCNVector3Value tint:nil];

    NSArray<NSValue *> *pinePositions=@[
        [NSValue valueWithSCNVector3:SCNVector3Make(-13,0,1)],
        [NSValue valueWithSCNVector3:SCNVector3Make(13,0,1)],
        [NSValue valueWithSCNVector3:SCNVector3Make(-12,0,10)],
        [NSValue valueWithSCNVector3:SCNVector3Make(12,0,10)]
    ];
    for (NSValue *value in pinePositions)
        [self addModel:@"converted/gaia/tree_pine_aleppo_1.obj"
                texture:@"textures/skins/gaia/aleppo_pine.png"
                  target:4.3 position:value.SCNVector3Value tint:nil];
}

- (void)addStartingUnits {
    NSArray<NSValue *> *bluePositions=@[
        [NSValue valueWithSCNVector3:SCNVector3Make(-8.4,0,3.8)],
        [NSValue valueWithSCNVector3:SCNVector3Make(-7.6,0,4.2)],
        [NSValue valueWithSCNVector3:SCNVector3Make(-6.8,0,3.8)]
    ];
    for (NSValue *value in bluePositions)
        [self addUnitAt:value.SCNVector3Value
                  tint:[UIColor colorWithRed:0.35 green:0.68 blue:1 alpha:1]
                 owner:YES];

    NSArray<NSValue *> *redPositions=@[
        [NSValue valueWithSCNVector3:SCNVector3Make(8.4,0,3.8)],
        [NSValue valueWithSCNVector3:SCNVector3Make(7.6,0,4.2)],
        [NSValue valueWithSCNVector3:SCNVector3Make(6.8,0,3.8)]
    ];
    for (NSValue *value in redPositions)
        [self addUnitAt:value.SCNVector3Value
                  tint:[UIColor colorWithRed:1 green:0.38 blue:0.3 alpha:1]
                 owner:NO];
}

- (void)addCamera {
    self.cameraNode=[SCNNode node];
    self.cameraNode.camera=[SCNCamera camera];
    self.cameraNode.camera.usesOrthographicProjection=YES;
    self.cameraNode.camera.orthographicScale=24;
    self.cameraNode.camera.zNear=0.1;
    self.cameraNode.camera.zFar=150;
    self.cameraNode.position=SCNVector3Make(0,18,21);
    self.cameraNode.eulerAngles=SCNVector3Make((float)-M_PI_4,0,0);
    [self.scene.rootNode addChildNode:self.cameraNode];
    self.sceneView.pointOfView=self.cameraNode;
}

- (void)addStatusOverlay {
    self.statusLabel=[UILabel new];
    self.statusLabel.translatesAutoresizingMaskIntoConstraints=NO;
    self.statusLabel.font=[UIFont systemFontOfSize:12 weight:UIFontWeightSemibold];
    self.statusLabel.textColor=UIColor.whiteColor;
    self.statusLabel.backgroundColor=[UIColor colorWithWhite:0 alpha:0.58];
    self.statusLabel.layer.cornerRadius=6;
    self.statusLabel.clipsToBounds=YES;
    self.statusLabel.textAlignment=NSTextAlignmentCenter;
    [self.sceneView addSubview:self.statusLabel];
    [NSLayoutConstraint activateConstraints:@[
        [self.statusLabel.topAnchor constraintEqualToAnchor:self.sceneView.safeAreaLayoutGuide.topAnchor constant:8],
        [self.statusLabel.centerXAnchor constraintEqualToAnchor:self.sceneView.centerXAnchor],
        [self.statusLabel.widthAnchor constraintGreaterThanOrEqualToConstant:210],
        [self.statusLabel.heightAnchor constraintEqualToConstant:28]
    ]];
    [self updateStatus];
}

- (void)updateStatus {
    if (!self.statusLabel) return;
    NSString *side=self.blueSideActive ? @"Blue" : @"Red";
    NSString *mode=@[ @"Select", @"Order", @"Pan" ][self.mode];
    NSString *selection=@"nothing selected";
    if (self.focusedAttackTarget && self.selectedUnits.count)
        selection=[NSString stringWithFormat:@"%lu hoplites attacking",(unsigned long)self.selectedUnits.count];
    else if (self.selectedUnits.count>1)
        selection=[NSString stringWithFormat:@"%lu hoplites selected",(unsigned long)self.selectedUnits.count];
    else if (self.selectedUnits.count==1)
        selection=@"1 hoplite selected";
    else if (self.selectedBuilding)
        selection=@"building selected";
    NSString *pad=self.movePad && !self.movePad.hidden ? @"  •  move pad on" : @"";
    self.statusLabel.text=[NSString stringWithFormat:@"  %@ settlement  •  %@  •  %@%@  ",side,mode,selection,pad];
}

- (SCNNode *)loadModel:(NSString *)mesh
               texture:(NSString *)texture
                 target:(CGFloat)target
                  tint:(UIColor *)tint {
    NSString *path=ArtPath(mesh);
    if (!path) return nil;
    NSError *error=nil;
    SCNScene *loaded=[SCNScene sceneWithURL:[NSURL fileURLWithPath:path]
                                    options:@{SCNSceneSourceConvertToYUpKey:@YES}
                                      error:&error];
    if (!loaded) {
        NSLog(@"OpenEmpire: could not load %@: %@",mesh,error.localizedDescription);
        return nil;
    }
    SCNNode *container=[SCNNode node];
    for (SCNNode *child in loaded.rootNode.childNodes)
        [container addChildNode:[child clone]];
    UIImage *image=ArtImage(texture);
    [self applyImage:image tint:tint toNode:container];

    SCNVector3 min,max;
    if (![container getBoundingBoxMin:&min max:&max]) return nil;
    CGFloat width=max.x-min.x, height=max.y-min.y, depth=max.z-min.z;
    CGFloat extent=MAX(width,MAX(height,depth));
    if (extent<0.001) return nil;
    CGFloat scale=target/extent;
    container.scale=SCNVector3Make((float)scale,(float)scale,(float)scale);
    container.position=SCNVector3Make(0,(float)(-min.y*scale),0);
    return container;
}

- (void)applyImage:(UIImage *)image tint:(UIColor *)tint toNode:(SCNNode *)node {
    if (node.geometry) {
        if (node.geometry.materials.count==0) node.geometry.firstMaterial=[SCNMaterial material];
        for (SCNMaterial *material in node.geometry.materials) {
            material.diffuse.contents=image ?: [UIColor colorWithWhite:0.85 alpha:1];
            material.diffuse.wrapS=SCNWrapModeClamp;
            material.diffuse.wrapT=SCNWrapModeClamp;
            material.lightingModelName=SCNLightingModelBlinn;
            material.doubleSided=YES;
            if (tint) material.multiply.contents=tint;
        }
    }
    [node enumerateChildNodesUsingBlock:^(SCNNode *child, BOOL *stop) {
        (void)stop;
        [self applyImage:image tint:tint toNode:child];
    }];
}

- (SCNNode *)addModel:(NSString *)mesh
              texture:(NSString *)texture
                target:(CGFloat)target
             position:(SCNVector3)position
                 tint:(UIColor *)tint {
    SCNNode *node=[self loadModel:mesh texture:texture target:target tint:tint];
    if (!node) return nil;
    node.position=SCNVector3Make(position.x,node.position.y,position.z);
    [self.world addChildNode:node];
    self.buildingCount++;
    return node;
}

- (SCNNode *)addBuilding:(NSString *)mesh
                 texture:(NSString *)texture
                   target:(CGFloat)target
                position:(SCNVector3)position
                    tint:(UIColor *)tint {
    SCNNode *building=[self addModel:mesh texture:texture target:target position:position tint:tint];
    if (building) {
        building.name=position.x < 0 ? @"building.blue" : @"building.red";
        [self.buildings addObject:building];
        self.hitPoints[NodeKey(building)]=@400;
    }
    return building;
}

- (SCNNode *)addUnitAt:(SCNVector3)position tint:(UIColor *)tint owner:(BOOL)blueOwner {
    SCNNode *unit=[self loadModel:@"converted/skeletal/new/m_armor_tunic_short.obj"
                           texture:@"textures/skins/skeletal/athen/linothorax_lamellar_01_03.png"
                             target:1.35 tint:tint];
    if (!unit) return nil;
    unit.name=blueOwner ? @"hoplite.blue" : @"hoplite.red";
    unit.position=SCNVector3Make(position.x,unit.position.y,position.z);
    [self.world addChildNode:unit];
    [self.units addObject:unit];
    self.hitPoints[NodeKey(unit)]=@100;
    self.unitCount++;
    return unit;
}

- (void)addSettlementMarkerAt:(SCNVector3)position title:(NSString *)title color:(UIColor *)color {
    SCNCylinder *base=[SCNCylinder cylinderWithRadius:0.28 height:0.08];
    base.firstMaterial=[SCNMaterial material];
    base.firstMaterial.diffuse.contents=color;
    SCNNode *baseNode=[SCNNode nodeWithGeometry:base];
    baseNode.position=SCNVector3Make(position.x,position.y-0.36,position.z);
    [self.world addChildNode:baseNode];

    SCNText *text=[SCNText textWithString:title extrusionDepth:0.015];
    text.font=[UIFont systemFontOfSize:0.7 weight:UIFontWeightBold];
    text.firstMaterial=[SCNMaterial material];
    text.firstMaterial.diffuse.contents=color;
    SCNNode *label=[SCNNode nodeWithGeometry:text];
    label.scale=SCNVector3Make(0.012,0.012,0.012);
    label.position=SCNVector3Make(position.x-0.85,position.y,position.z);
    label.constraints=@[[SCNBillboardConstraint billboardConstraint]];
    [self.world addChildNode:label];
}

- (void)installGestures {
    UITapGestureRecognizer *tap=[[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(handleTap:)];
    [self.sceneView addGestureRecognizer:tap];
    UITapGestureRecognizer *doubleTap=[[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(handleDoubleTap:)];
    doubleTap.numberOfTapsRequired=2;
    [self.sceneView addGestureRecognizer:doubleTap];
    [tap requireGestureRecognizerToFail:doubleTap];
    UIPanGestureRecognizer *pan=[[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(handlePan:)];
    pan.maximumNumberOfTouches=2;
    [self.sceneView addGestureRecognizer:pan];
    UIPinchGestureRecognizer *pinch=[[UIPinchGestureRecognizer alloc] initWithTarget:self action:@selector(handlePinch:)];
    [self.sceneView addGestureRecognizer:pinch];
}

- (UIButton *)controlButton:(NSString *)title selector:(SEL)selector {
    UIButton *button=[UIButton buttonWithType:UIButtonTypeSystem];
    UIButtonConfiguration *config=[UIButtonConfiguration filledButtonConfiguration];
    config.title=title;
    config.baseBackgroundColor=[UIColor colorWithWhite:0.08 alpha:0.9];
    config.baseForegroundColor=UIColor.whiteColor;
    config.cornerStyle=UIButtonConfigurationCornerStyleMedium;
    config.contentInsets=NSDirectionalEdgeInsetsMake(4,8,4,8);
    button.configuration=config;
    button.translatesAutoresizingMaskIntoConstraints=NO;
    [button addTarget:self action:selector forControlEvents:UIControlEventTouchUpInside];
    return button;
}

- (void)installControls {
    self.movePad=[UIView new];
    self.movePad.translatesAutoresizingMaskIntoConstraints=NO;
    self.movePad.backgroundColor=UIColor.clearColor;
    self.movePad.hidden=YES;
    [self.sceneView addSubview:self.movePad];
    [NSLayoutConstraint activateConstraints:@[
        [self.movePad.trailingAnchor constraintEqualToAnchor:self.sceneView.safeAreaLayoutGuide.trailingAnchor constant:-18],
        [self.movePad.bottomAnchor constraintEqualToAnchor:self.sceneView.safeAreaLayoutGuide.bottomAnchor constant:-112],
        [self.movePad.widthAnchor constraintEqualToConstant:156],
        [self.movePad.heightAnchor constraintEqualToConstant:156]
    ]];

    self.moveStick=[[OEThumbstickView alloc] initWithFrame:CGRectZero];
    self.moveStick.translatesAutoresizingMaskIntoConstraints=NO;
    [self.movePad addSubview:self.moveStick];
    [NSLayoutConstraint activateConstraints:@[
        [self.moveStick.leadingAnchor constraintEqualToAnchor:self.movePad.leadingAnchor],
        [self.moveStick.trailingAnchor constraintEqualToAnchor:self.movePad.trailingAnchor],
        [self.moveStick.topAnchor constraintEqualToAnchor:self.movePad.topAnchor],
        [self.moveStick.bottomAnchor constraintEqualToAnchor:self.movePad.bottomAnchor]
    ]];

    self.moveStickDisplayLink=[CADisplayLink displayLinkWithTarget:self selector:@selector(moveStickTick:)];
    [self.moveStickDisplayLink addToRunLoop:[NSRunLoop mainRunLoop] forMode:NSRunLoopCommonModes];

    self.movePadToggle=[UIButton buttonWithType:UIButtonTypeSystem];
    self.movePadToggle.translatesAutoresizingMaskIntoConstraints=NO;
    UIButtonConfiguration *toggleConfig=[UIButtonConfiguration filledButtonConfiguration];
    toggleConfig.baseBackgroundColor=[UIColor colorWithRed:0.12 green:0.33 blue:0.46 alpha:0.96];
    toggleConfig.baseForegroundColor=UIColor.whiteColor;
    toggleConfig.cornerStyle=UIButtonConfigurationCornerStyleCapsule;
    toggleConfig.image=[UIImage systemImageNamed:@"gamecontroller.fill"];
    toggleConfig.title=@" MOVE";
    self.movePadToggle.configuration=toggleConfig;
    self.movePadToggle.accessibilityLabel=@"Toggle movement pad";
    [self.movePadToggle addTarget:self action:@selector(toggleMovePad) forControlEvents:UIControlEventTouchUpInside];
    [self.sceneView addSubview:self.movePadToggle];
    [NSLayoutConstraint activateConstraints:@[
        [self.movePadToggle.trailingAnchor constraintEqualToAnchor:self.sceneView.safeAreaLayoutGuide.trailingAnchor constant:-12],
        [self.movePadToggle.bottomAnchor constraintEqualToAnchor:self.sceneView.safeAreaLayoutGuide.bottomAnchor constant:-58],
        [self.movePadToggle.widthAnchor constraintEqualToConstant:82],
        [self.movePadToggle.heightAnchor constraintEqualToConstant:42]
    ]];

    self.zoomInButton=[self controlButton:@"+" selector:@selector(zoomIn)];
    self.zoomOutButton=[self controlButton:@"−" selector:@selector(zoomOut)];
    self.zoomInButton.accessibilityLabel=@"Zoom in";
    self.zoomOutButton.accessibilityLabel=@"Zoom out";
    [self.sceneView addSubview:self.zoomInButton]; [self.sceneView addSubview:self.zoomOutButton];
    [NSLayoutConstraint activateConstraints:@[
        [self.zoomInButton.trailingAnchor constraintEqualToAnchor:self.sceneView.safeAreaLayoutGuide.trailingAnchor constant:-14],
        [self.zoomInButton.topAnchor constraintEqualToAnchor:self.sceneView.safeAreaLayoutGuide.topAnchor constant:48],
        [self.zoomInButton.widthAnchor constraintEqualToConstant:42], [self.zoomInButton.heightAnchor constraintEqualToConstant:38],
        [self.zoomOutButton.trailingAnchor constraintEqualToAnchor:self.sceneView.safeAreaLayoutGuide.trailingAnchor constant:-14],
        [self.zoomOutButton.topAnchor constraintEqualToAnchor:self.zoomInButton.bottomAnchor constant:6],
        [self.zoomOutButton.widthAnchor constraintEqualToConstant:42], [self.zoomOutButton.heightAnchor constraintEqualToConstant:38]
    ]];
}

- (SCNNode *)unitForNode:(SCNNode *)node {
    while (node) {
        if ([self.units containsObject:node]) return node;
        node=node.parentNode;
    }
    return nil;
}

- (SCNNode *)buildingForNode:(SCNNode *)node {
    while (node) {
        if ([self.buildings containsObject:node]) return node;
        node=node.parentNode;
    }
    return nil;
}

- (BOOL)nodeBelongsToActiveSide:(SCNNode *)node {
    if (!node.name.length) return NO;
    NSString *suffix=self.blueSideActive ? @".blue" : @".red";
    return [node.name hasSuffix:suffix];
}

- (NSString *)unitTypeForNode:(SCNNode *)unit {
    NSString *name=unit.name ?: @"unit";
    NSArray<NSString *> *parts=[name componentsSeparatedByString:@"."];
    return parts.firstObject ?: name;
}

- (void)cancelAttacks {
    [self.attackTargets removeAllObjects];
    [self.nextAttackTimes removeAllObjects];
    self.focusedAttackTarget=nil;
}

- (void)clearSelection {
    for (SCNNode *ring in self.selectionRings) [ring removeFromParentNode];
    [self.selectionRings removeAllObjects];
    [self cancelAttacks];
    [self.selectedUnits removeAllObjects];
    self.selectionRing=nil;
    self.selectedUnit=nil;
    self.selectedBuilding=nil;
}

- (SCNNode *)selectionRingForNode:(SCNNode *)node unit:(BOOL)unit {
    SCNTorus *torus=[SCNTorus torusWithRingRadius:unit ? 0.52 : 1.15 pipeRadius:0.045];
    torus.firstMaterial=[SCNMaterial material];
    torus.firstMaterial.diffuse.contents=unit ? [UIColor colorWithRed:0.35 green:0.9 blue:1 alpha:1] : [UIColor colorWithRed:1 green:0.8 blue:0.2 alpha:1];
    torus.firstMaterial.emission.contents=unit ? [UIColor colorWithRed:0.1 green:0.45 blue:0.7 alpha:1] : [UIColor colorWithRed:0.55 green:0.3 blue:0.05 alpha:1];
    SCNNode *ring=[SCNNode nodeWithGeometry:torus];
    ring.eulerAngles=SCNVector3Make((float)M_PI_2,0,0);
    ring.position=SCNVector3Make(0,0.06,0);
    [node addChildNode:ring];
    [self.selectionRings addObject:ring];
    return ring;
}

- (void)selectUnits:(NSArray<SCNNode *> *)units {
    [self clearSelection];
    for (SCNNode *unit in units)
        if ([self.units containsObject:unit] && [self nodeBelongsToActiveSide:unit])
            [self.selectedUnits addObject:unit];
    if (!self.selectedUnits.count) { [self updateStatus]; return; }
    self.selectedUnit=self.selectedUnits.firstObject;
    for (SCNNode *unit in self.selectedUnits) {
        SCNNode *ring=[self selectionRingForNode:unit unit:YES];
        if (!self.selectionRing) self.selectionRing=ring;
    }
    [self updateStatus];
}

- (void)selectUnit:(SCNNode *)unit {
    [self selectUnits:unit ? @[unit] : @[]];
}

- (void)selectBuilding:(SCNNode *)building {
    [self clearSelection];
    self.selectedBuilding=([self.buildings containsObject:building] && [self nodeBelongsToActiveSide:building]) ? building : nil;
    if (self.selectedBuilding) [self selectionRingForNode:self.selectedBuilding unit:NO];
    [self updateStatus];
}

- (SCNNode *)nodeForKey:(NSValue *)key {
    const void *pointer=key.pointerValue;
    for (SCNNode *unit in self.units)
        if ((__bridge const void *)unit==pointer) return unit;
    for (SCNNode *building in self.buildings)
        if ((__bridge const void *)building==pointer) return building;
    return nil;
}

- (void)destroyTarget:(SCNNode *)target {
    if (!target) return;
    NSArray<NSValue *> *keys=[self.attackTargets.allKeys copy];
    for (NSValue *key in keys) {
        if (self.attackTargets[key]==target) {
            [self.nextAttackTimes removeObjectForKey:key];
            [self.attackTargets removeObjectForKey:key];
        }
    }
    [self.hitPoints removeObjectForKey:NodeKey(target)];
    [self.units removeObject:target];
    [self.buildings removeObject:target];
    if (self.focusedAttackTarget==target) self.focusedAttackTarget=nil;
    [target removeAllActions];
    [target runAction:[SCNAction sequence:@[
        [SCNAction fadeOutWithDuration:0.25],
        [SCNAction removeFromParentNode]
    ]]];
}

- (void)applyDamage:(NSInteger)damage toTarget:(SCNNode *)target {
    NSInteger health=self.hitPoints[NodeKey(target)].integerValue-damage;
    [target runAction:[SCNAction sequence:@[
        [SCNAction fadeOpacityTo:0.35 duration:0.06],
        [SCNAction fadeOpacityTo:1.0 duration:0.12]
    ]] forKey:@"hit-flash"];
    if (health<=0) {
        [self destroyTarget:target];
        [self updateStatus];
        return;
    }
    self.hitPoints[NodeKey(target)]=@(health);
}

- (void)attackTarget:(SCNNode *)target {
    if (!target || [self nodeBelongsToActiveSide:target]) return;
    if (!self.selectedUnits.count) {
        self.focusedAttackTarget=nil;
        [self updateStatus];
        return;
    }
    [self cancelAttacks];
    self.focusedAttackTarget=target;
    NSUInteger index=0;
    for (SCNNode *unit in [self.selectedUnits copy]) {
        if (![self nodeBelongsToActiveSide:unit]) continue;
        CGFloat dx=unit.position.x-target.position.x;
        CGFloat dz=unit.position.z-target.position.z;
        CGFloat distance=hypot(dx,dz);
        if (distance<0.001) { dx=1; dz=0; distance=1; }
        CGFloat approach=1.35+(CGFloat)(index%3)*0.28;
        SCNVector3 destination=SCNVector3Make(target.position.x+(float)(dx/distance*approach),
                                              unit.position.y,
                                              target.position.z+(float)(dz/distance*approach));
        NSTimeInterval duration=MIN(1.5,MAX(0.35,distance*0.12));
        [unit removeActionForKey:@"move"];
        [unit runAction:[SCNAction moveTo:destination duration:duration] forKey:@"move"];
        self.attackTargets[NodeKey(unit)]=target;
        self.nextAttackTimes[NodeKey(unit)]=@0;
        index++;
    }
    [self updateStatus];
}

- (void)processAttacksAtTime:(NSTimeInterval)time {
    if (!self.attackTargets.count) return;
    NSArray<NSValue *> *keys=[self.attackTargets.allKeys copy];
    for (NSValue *key in keys) {
        SCNNode *attacker=[self nodeForKey:key];
        SCNNode *target=self.attackTargets[key];
        if (!attacker || !target || !attacker.parentNode || !target.parentNode || !self.hitPoints[NodeKey(target)]) {
            [self.attackTargets removeObjectForKey:key];
            [self.nextAttackTimes removeObjectForKey:key];
            continue;
        }
        CGFloat dx=attacker.presentationNode.position.x-target.presentationNode.position.x;
        CGFloat dz=attacker.presentationNode.position.z-target.presentationNode.position.z;
        if (hypot(dx,dz)>2.25) continue;
        NSTimeInterval next=self.nextAttackTimes[key].doubleValue;
        if (time<next) continue;
        NSInteger damage=[self.buildings containsObject:target] ? 18 : 34;
        [self applyDamage:damage toTarget:target];
        if (self.attackTargets[key]) self.nextAttackTimes[key]=@(time+0.7);
    }
}

- (void)moveSelectedUnitsTo:(SCNVector3)worldPoint {
    if (!self.selectedUnits.count) return;
    [self cancelAttacks];
    for (NSUInteger i=0;i<self.selectedUnits.count;++i) {
        SCNNode *unit=self.selectedUnits[i];
        CGFloat column=(CGFloat)(i%3)-1.0;
        CGFloat row=(CGFloat)(i/3);
        SCNVector3 target=SCNVector3Make(worldPoint.x+(float)(column*0.55),
                                         unit.position.y,
                                         worldPoint.z+(float)(row*0.55));
        [unit runAction:[SCNAction moveTo:target duration:0.45]];
    }
}

- (void)handleTap:(UITapGestureRecognizer *)recognizer {
    if (recognizer.state!=UIGestureRecognizerStateEnded || !self.running) return;
    NSArray<SCNHitTestResult *> *hits=[self.sceneView hitTest:[recognizer locationInView:self.sceneView] options:nil];
    SCNNode *unit=nil;
    SCNNode *building=nil;
    SCNVector3 worldPoint=SCNVector3Make(0,0,0);
    BOOL havePoint=NO;
    for (SCNHitTestResult *hit in hits) {
        if (!havePoint) { worldPoint=hit.worldCoordinates; havePoint=YES; }
        SCNNode *candidate=[self unitForNode:hit.node];
        if (candidate) { unit=candidate; break; }
        SCNNode *candidateBuilding=[self buildingForNode:hit.node];
        if (candidateBuilding) { building=candidateBuilding; break; }
    }
    if (self.mode==OEArtModeSelect) {
        if (unit && [self nodeBelongsToActiveSide:unit]) [self selectUnit:unit];
        else if (building && [self nodeBelongsToActiveSide:building]) [self selectBuilding:building];
        else [self selectUnit:nil];
    } else if (self.mode==OEArtModeOrder) {
        if (unit) {
            if ([self nodeBelongsToActiveSide:unit]) [self selectUnit:unit];
            else [self attackTarget:unit];
        } else if (building) {
            if ([self nodeBelongsToActiveSide:building]) [self selectBuilding:building];
            else [self attackTarget:building];
        } else if (havePoint) [self moveSelectedUnitsTo:worldPoint];
    }
}

- (void)handleDoubleTap:(UITapGestureRecognizer *)recognizer {
    if (recognizer.state!=UIGestureRecognizerStateEnded || !self.running) return;
    NSArray<SCNHitTestResult *> *hits=[self.sceneView hitTest:[recognizer locationInView:self.sceneView] options:nil];
    SCNNode *unit=nil;
    for (SCNHitTestResult *hit in hits) {
        unit=[self unitForNode:hit.node];
        if (unit) break;
    }
    if (!unit) return;
    if (![self nodeBelongsToActiveSide:unit]) return;
    NSString *type=[self unitTypeForNode:unit];
    NSMutableArray<SCNNode *> *sameType=[NSMutableArray array];
    for (SCNNode *candidate in self.units) {
        NSString *candidateType=[self unitTypeForNode:candidate];
        if ([self nodeBelongsToActiveSide:candidate] && [candidateType isEqualToString:type])
            [sameType addObject:candidate];
    }
    [self selectUnits:sameType];
}

- (void)renderer:(id<SCNSceneRenderer>)renderer updateAtTime:(NSTimeInterval)time {
    (void)renderer;
    if (self.running) [self processAttacksAtTime:time];
}

- (void)handlePan:(UIPanGestureRecognizer *)recognizer {
    if (!self.running || recognizer.state!=UIGestureRecognizerStateChanged) return;
    if (self.mode!=OEArtModePan && recognizer.numberOfTouches<2) return;
    CGPoint translation=[recognizer translationInView:self.sceneView];
    CGFloat scale=self.cameraNode.camera.orthographicScale/MAX(1.0,self.sceneView.bounds.size.width);
    self.cameraNode.position=SCNVector3Make(self.cameraNode.position.x-(float)(translation.x*scale),
                                            self.cameraNode.position.y,
                                            self.cameraNode.position.z+(float)(translation.y*scale));
    [recognizer setTranslation:CGPointZero inView:self.sceneView];
}

- (void)handlePinch:(UIPinchGestureRecognizer *)recognizer {
    if (!self.running || recognizer.state!=UIGestureRecognizerStateChanged) return;
    CGFloat scale=self.cameraNode.camera.orthographicScale/recognizer.scale;
    self.cameraNode.camera.orthographicScale=MAX(5,MIN(48,scale));
    recognizer.scale=1;
}

- (void)moveStickTick:(CADisplayLink *)link {
    (void)link;
    if (!self.running || self.movePad.hidden || !self.moveStick) return;
    CGPoint value=self.moveStick.value;
    if (fabs(value.x)<0.04 && fabs(value.y)<0.04) return;
    if (self.selectedUnits.count) {
        if (self.attackTargets.count) [self cancelAttacks];
        CGFloat amount=0.095;
        for (SCNNode *unit in self.selectedUnits) {
            [unit removeActionForKey:@"move"];
            unit.position=SCNVector3Make(unit.position.x+(float)(value.x*amount),
                                         unit.position.y,
                                         unit.position.z+(float)(value.y*amount));
        }
    } else {
        CGFloat scale=self.cameraNode.camera.orthographicScale/MAX(1.0,self.sceneView.bounds.size.width);
        self.cameraNode.position=SCNVector3Make(self.cameraNode.position.x-(float)(value.x*scale*5.0),
                                                self.cameraNode.position.y,
                                                self.cameraNode.position.z+(float)(value.y*scale*5.0));
    }
}

- (void)toggleMovePad {
    self.movePad.hidden=!self.movePad.hidden;
    [self updateStatus];
}

- (void)nudgeSelectedUnitsBy:(SCNVector3)delta {
    if (!self.selectedUnits.count) return;
    for (SCNNode *unit in self.selectedUnits) {
        SCNVector3 target=SCNVector3Make(unit.position.x+delta.x,unit.position.y,unit.position.z+delta.z);
        [unit runAction:[SCNAction moveTo:target duration:0.2]];
    }
}

- (void)nudgeUp { [self nudgeSelectedUnitsBy:SCNVector3Make(0,0,-0.8)]; }
- (void)nudgeDown { [self nudgeSelectedUnitsBy:SCNVector3Make(0,0,0.8)]; }
- (void)nudgeLeft { [self nudgeSelectedUnitsBy:SCNVector3Make(-0.8,0,0)]; }
- (void)nudgeRight { [self nudgeSelectedUnitsBy:SCNVector3Make(0.8,0,0)]; }

- (void)zoomIn {
    if (self.running) self.cameraNode.camera.orthographicScale=MAX(5,self.cameraNode.camera.orthographicScale*0.72);
}

- (void)zoomOut {
    if (self.running) self.cameraNode.camera.orthographicScale=MIN(48,self.cameraNode.camera.orthographicScale*1.25);
}

- (void)selectMode {
    self.mode=OEArtModeSelect;
    [self updateStatus];
}

- (void)orderMode {
    self.mode=OEArtModeOrder;
    [self updateStatus];
}

- (void)panMode {
    self.mode=OEArtModePan;
    [self updateStatus];
}

- (void)centerCamera {
    self.mapVisible=NO;
    self.cameraNode.position=SCNVector3Make(0,18,21);
    self.cameraNode.eulerAngles=SCNVector3Make((float)-M_PI_4,0,0);
    self.cameraNode.camera.orthographicScale=24;
}

- (void)toggleMap {
    if (!self.running) return;
    self.mapVisible=!self.mapVisible;
    if (self.mapVisible) {
        self.cameraNode.position=SCNVector3Make(0,32,0);
        self.cameraNode.eulerAngles=SCNVector3Make((float)-M_PI_2,0,0);
        self.cameraNode.camera.orthographicScale=36;
    } else {
        [self centerCamera];
    }
    [self updateStatus];
}

- (void)showActionsFromViewController:(UIViewController *)controller {
    if (!self.running || controller.presentedViewController) return;
    self.sceneView.playing=NO;
    UIAlertController *alert=[UIAlertController alertControllerWithTitle:@"Settlement actions"
                                                                   message:@"These actions place more real 0 A.D. art into the offline sandbox."
                                                            preferredStyle:UIAlertControllerStyleActionSheet];
    __weak OEArtDemo *weakSelf=self;
    [alert addAction:[UIAlertAction actionWithTitle:@"Build house" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        (void)action; [weakSelf buildHouse]; [weakSelf resumeAfterAlert];
    }]];
    [alert addAction:[UIAlertAction actionWithTitle:@"Train hoplite" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        (void)action; [weakSelf trainUnit]; [weakSelf resumeAfterAlert];
    }]];
    [alert addAction:[UIAlertAction actionWithTitle:@"Plant oak" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        (void)action; [weakSelf plantOak]; [weakSelf resumeAfterAlert];
    }]];
    [alert addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:^(UIAlertAction *action) {
        (void)action; [weakSelf resumeAfterAlert];
    }]];
    [self configurePopover:alert source:controller.view];
    [controller presentViewController:alert animated:YES completion:nil];
}

- (void)showMenuFromViewController:(UIViewController *)controller {
    if (!self.running || controller.presentedViewController) return;
    self.sceneView.playing=NO;
    UIAlertController *alert=[UIAlertController alertControllerWithTitle:@"Sandbox paused"
                                                                   message:@"There is no network or strategic AI opponent. You can control either settlement."
                                                            preferredStyle:UIAlertControllerStyleActionSheet];
    __weak OEArtDemo *weakSelf=self;
    [alert addAction:[UIAlertAction actionWithTitle:@"Resume" style:UIAlertActionStyleCancel handler:^(UIAlertAction *action) {
        (void)action; [weakSelf resumeAfterAlert];
    }]];
    [alert addAction:[UIAlertAction actionWithTitle:@"Center camera" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        (void)action; [weakSelf centerCamera]; [weakSelf resumeAfterAlert];
    }]];
    [alert addAction:[UIAlertAction actionWithTitle:@"Switch Blue / Red" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        (void)action; weakSelf.blueSideActive=!weakSelf.blueSideActive; [weakSelf selectUnit:nil]; [weakSelf updateStatus]; [weakSelf resumeAfterAlert];
    }]];
    [alert addAction:[UIAlertAction actionWithTitle:@"End sandbox" style:UIAlertActionStyleDestructive handler:^(UIAlertAction *action) {
        (void)action;
        [weakSelf stop];
        if (weakSelf.onEnd) weakSelf.onEnd();
    }]];
    [self configurePopover:alert source:controller.view];
    [controller presentViewController:alert animated:YES completion:nil];
}

- (void)configurePopover:(UIAlertController *)alert source:(UIView *)source {
    alert.popoverPresentationController.sourceView=source;
    alert.popoverPresentationController.sourceRect=source.bounds;
    alert.popoverPresentationController.permittedArrowDirections=UIPopoverArrowDirectionDown;
}

- (void)resumeAfterAlert {
    if (self.running) self.sceneView.playing=YES;
}

- (void)buildHouse {
    CGFloat side=self.blueSideActive ? -1 : 1;
    CGFloat offset=1.4+(CGFloat)(self.buildingCount%4)*0.75;
    [self addBuilding:@"converted/props/hele_house_a_struct.obj"
              texture:@"textures/skins/structural/hele_struct.png"
                target:2.4 position:SCNVector3Make(side*(6.2+offset),0,1.8) tint:nil];
}

- (void)trainUnit {
    CGFloat side=self.blueSideActive ? -1 : 1;
    CGFloat offset=1.2+(CGFloat)(self.unitCount%3)*0.7;
    [self addUnitAt:SCNVector3Make(side*(7.0+offset),0,4.0+(CGFloat)(self.unitCount%2)*0.4)
               tint:self.blueSideActive ? [UIColor colorWithRed:0.35 green:0.68 blue:1 alpha:1] : [UIColor colorWithRed:1 green:0.38 blue:0.3 alpha:1]
              owner:self.blueSideActive];
}

- (void)plantOak {
    CGFloat side=self.blueSideActive ? -1 : 1;
    CGFloat offset=3.0+(CGFloat)(self.buildingCount%3)*1.2;
    [self addModel:@"converted/gaia/oak_tree_a.obj"
            texture:@"textures/skins/gaia/oak_tree_a.png"
              target:3.9 position:SCNVector3Make(side*offset,0,7.0) tint:nil];
}

@end
