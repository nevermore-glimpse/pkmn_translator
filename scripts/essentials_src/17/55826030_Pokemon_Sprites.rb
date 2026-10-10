#===============================================================================
# Pokémon sprite (used out of battle)
#===============================================================================
class PokemonSprite < SpriteWrapper
  def initialize(viewport=nil)
    super(viewport)
    @_iconbitmap=nil
  end

  def dispose
    @_iconbitmap.dispose if @_iconbitmap
    @_iconbitmap=nil
    self.bitmap=nil if !self.disposed?
    super
  end

  def update
    super
    if @_iconbitmap
      @_iconbitmap.update
      self.bitmap=@_iconbitmap.bitmap
    end
  end

  def clearBitmap
    @_iconbitmap.dispose if @_iconbitmap
    @_iconbitmap=nil
    self.bitmap=nil
  end

  def setOffset(offset=PictureOrigin::Center)
    @offset=offset
    changeOrigin
  end

  def changeOrigin
    return if !self.bitmap
    @offset=PictureOrigin::Center if !@offset
    case @offset
    when PictureOrigin::TopLeft, PictureOrigin::Top, PictureOrigin::TopRight
      self.oy=0
    when PictureOrigin::Left, PictureOrigin::Center, PictureOrigin::Right
      self.oy=self.bitmap.height/2
    when PictureOrigin::BottomLeft, PictureOrigin::Bottom, PictureOrigin::BottomRight
      self.oy=self.bitmap.height
    end
    case @offset
    when PictureOrigin::TopLeft, PictureOrigin::Left, PictureOrigin::BottomLeft
      self.ox=0
    when PictureOrigin::Top, PictureOrigin::Center, PictureOrigin::Bottom
      self.ox=self.bitmap.width/2
    when PictureOrigin::TopRight, PictureOrigin::Right, PictureOrigin::BottomRight
      self.ox=self.bitmap.width
    end
  end

  def setPokemonBitmap(pokemon,back=false)
    @_iconbitmap.dispose if @_iconbitmap
    @_iconbitmap=pokemon ? pbLoadPokemonBitmap(pokemon,back) : nil
    self.bitmap=@_iconbitmap ? @_iconbitmap.bitmap : nil
    self.color=Color.new(0,0,0,0)
    changeOrigin
  end

  def setPokemonBitmapSpecies(pokemon,species,back=false)
    @_iconbitmap.dispose if @_iconbitmap
    @_iconbitmap=pokemon ? pbLoadPokemonBitmapSpecies(pokemon,species,back) : nil
    self.bitmap=@_iconbitmap ? @_iconbitmap.bitmap : nil
    changeOrigin
  end

  def setSpeciesBitmap(species,female=false,form=0,shiny=false,shadow=false,back=false,egg=false)
    @_iconbitmap.dispose if @_iconbitmap
    @_iconbitmap=pbLoadSpeciesBitmap(species,female,form,shiny,shadow,back,egg)
    self.bitmap=@_iconbitmap ? @_iconbitmap.bitmap : nil
    changeOrigin
  end
end



#===============================================================================
# Pokémon sprite (used in battle)
#===============================================================================
class PokemonBattlerSprite < RPG::Sprite
  attr_accessor :selected

  def initialize(doublebattle,index,viewport=nil)
    super(viewport)
    @selected=0
    @frame=0
    @index=index
    @updating=false
    @doublebattle=doublebattle
    @index=index
    @spriteX=0
    @spriteY=0
    @spriteXExtra=0
    @spriteYExtra=0
    @spriteVisible=false
    @_iconbitmap=nil
    self.visible=false
  end

  def x
    return @spriteX
  end

  def y
    return @spriteY
  end

  def x=(value)
    @spriteX=value
    super(value+@spriteXExtra)
  end

  def y=(value)
    @spriteY=value
    super(value+@spriteYExtra)
  end

  def width; return (self.bitmap) ? self.bitmap.width : 0; end
  def height; return (self.bitmap) ? self.bitmap.height : 0; end

  def dispose
    @_iconbitmap.dispose if @_iconbitmap
    @_iconbitmap=nil
    self.bitmap=nil if !self.disposed?
    super
  end

  def selected=(value)
    if @selected==1 && value!=1 && @spriteYExtra>0
      @spriteYExtra=0
      self.y=@spriteY
    end
    @selected=value
  end

  def visible=(value)
    @spriteVisible=value if !@updating
    super
  end

  def setPokemonBitmap(pokemon,back=false)
    @_iconbitmap.dispose if @_iconbitmap
    @_iconbitmap=pbLoadPokemonBitmap(pokemon,back)
    self.bitmap=@_iconbitmap ? @_iconbitmap.bitmap : nil
  end

  def setPokemonBitmapSpecies(pokemon,species,back=false)
    @_iconbitmap.dispose if @_iconbitmap
    @_iconbitmap=pbLoadPokemonBitmapSpecies(pokemon,species,back)
    self.bitmap=@_iconbitmap ? @_iconbitmap.bitmap : nil
  end

  def update
    @frame = (@frame+1)%24
    @updating=true
    @spriteYExtra=0
    # Pokémon sprite bobbing while Pokémon is selected
    if @selected==1 # When choosing commands for this Pokémon
      if (@frame/6).floor==1
        @spriteYExtra=2
      elsif (@frame/6).floor==3
        @spriteYExtra=-2
      end
    end
    self.x=@spriteX
    self.y=@spriteY
    self.visible=@spriteVisible
    # Pokémon sprite blinking when targeted or damaged
    if @spriteVisible
      if @selected==2 # When targeted
        self.visible=(@frame%12<8)
      elsif @selected==3 # When damaged
        self.visible=(@frame%12<8)
      end
    end
    if @_iconbitmap
      @_iconbitmap.update
      self.bitmap=@_iconbitmap.bitmap
    end
    @updating=false
  end
end



#===============================================================================
# Pokémon icon (for defined Pokémon)
#===============================================================================
class PokemonIconSprite < SpriteWrapper
  attr_accessor :selected
  attr_accessor :active
  attr_reader :pokemon

  def initialize(pokemon,viewport=nil)
    super(viewport)
    @animbitmap=nil
    @frames=[
       Rect.new(0,0,64,64),
       Rect.new(64,0,64,64)
    ]
    @selected=false
    @animframe=0
    @active=false
    self.pokemon=pokemon
    @frame=0
    @pokemon=pokemon
    @adjusted_x=0
    @adjusted_y=0
    @logical_x=0
    @logical_y=0
  end

  def pokemon=(value)
    @pokemon=value
    @animbitmap.dispose if @animbitmap
    @animbitmap=nil
    if @pokemon
      @animbitmap=AnimatedBitmap.new(pbPokemonIconFile(value))
      self.bitmap=@animbitmap.bitmap
      self.src_rect=@frames[@animframe]
    else
      self.bitmap=nil
    end
  end

  def dispose
    @animbitmap.dispose if @animbitmap
    super
  end

  def x
    @logical_x
  end

  def y
    @logical_y
  end

  def x=(value)
    @logical_x=value
    super(@logical_x+@adjusted_x)
  end

  def y=(value)
    @logical_y=value
    super(@logical_y+@adjusted_y)
  end

  def update
    @updating=true
    super
    if @animbitmap
      @animbitmap.update
      self.bitmap=@animbitmap.bitmap 
      self.src_rect=@frames[@animframe]
    end
    self.color=Color.new(0,0,0,0)
    frameskip=5
    frameskip=10 if @pokemon && @pokemon.hp<=(@pokemon.totalhp/2)
    frameskip=20 if @pokemon && @pokemon.hp<=(@pokemon.totalhp/4)
    frameskip=-1 if @pokemon && @pokemon.hp==0
    if frameskip==-1
      @animframe=0
      self.src_rect=@frames[@animframe]
    else
      @frame+=1
      @frame=0 if @frame>100
      if @frame>=frameskip
        @animframe=(@animframe==1) ? 0 : 1
        self.src_rect=@frames[@animframe]
        @frame=0
      end
    end
    if self.selected
      @adjusted_x=4
      @adjusted_y=(@animframe==0) ? -2 : 6
    else
      @adjusted_x=0
      @adjusted_y=0
    end
    @updating=false
    self.x=self.x
    self.y=self.y
  end
end



#===============================================================================
# Pokémon icon (for species)
#===============================================================================
class PokemonSpeciesIconSprite < SpriteWrapper
  attr_accessor :selected
  attr_accessor :active
  attr_reader :species
  attr_reader :gender
  attr_reader :form
  attr_reader :x
  attr_reader :y

  def initialize(species,viewport=nil)
    super(viewport)
    @animbitmap=nil
    @frames=[
       Rect.new(0,0,64,64),
       Rect.new(64,0,64,64)
    ]
    @animframe=0
    @frame=0
    @x=0
    @y=0
    @species=species
    @gender=0
    @form=0
    refresh
  end

  def species=(value)
    @species=value
    refresh
  end

  def gender=(value)
    @gender=value
    refresh
  end

  def form=(value)
    @form=value
    refresh
  end

  def pbSetParams(species,gender,form)
    @species=species
    @gender=gender
    @form=form
    refresh
  end

  def dispose
    @animbitmap.dispose if @animbitmap
    super
  end

  def x=(value)
    @x=value
    super(@x)
  end

  def y=(value)
    @y=value
    super(@y)
  end

  def refresh
    @animbitmap.dispose if @animbitmap
    @animbitmap=nil
    bitmapFileName=pbCheckPokemonIconFiles([@species,(@gender==1),false,@form,false])
    @animbitmap=AnimatedBitmap.new(bitmapFileName)
    self.bitmap=@animbitmap.bitmap
    self.src_rect=@frames[@animframe]
  end

  def update
    @updating=true
    super
    if @animbitmap
      @animbitmap.update
      self.bitmap=@animbitmap.bitmap 
      self.src_rect=@frames[@animframe]
    end
    frameskip=5
    @frame+=1
    @frame=0 if @frame>10
    if @frame>=frameskip
      @animframe=(@animframe==1) ? 0 : 1
      self.src_rect=@frames[@animframe]
      @frame=0
    end
    @updating=false
    self.x=self.x
    self.y=self.y
  end
end



#===============================================================================
# Sprite position adjustments
#===============================================================================
def getBattleSpriteMetricOffset(species,index,metrics=nil)
  metrics = load_data("Data/metrics.dat") if !metrics
  ret = 0
  if index==1 || index==3   # Foe Pokémon
    ret += (metrics[1][species] || 0)*2 # enemy Y
    ret -= (metrics[2][species] || 0)*2 # altitude
  else                      # Player's Pokémon
    ret += (metrics[0][species] || 0)*2
  end
  return ret
end

def adjustBattleSpriteY(sprite,species,index,metrics=nil)
  ret = 0
  spriteheight = (sprite.bitmap && !sprite.bitmap.disposed?) ? sprite.bitmap.height : 128
  ret -= spriteheight
  ret += getBattleSpriteMetricOffset(species,index,metrics)
  return ret
end

def pbPositionPokemonSprite(sprite,left,top)
  if sprite.bitmap && !sprite.bitmap.disposed?
    sprite.x = left+(128-sprite.bitmap.width)/2
    sprite.y = top+(128-sprite.bitmap.height)/2
  else
    sprite.x = left
    sprite.y = top
  end
end

def pbSpriteSetCenter(sprite,cx,cy)
  return if !sprite
  if !sprite.bitmap
    sprite.x = cx
    sprite.y = cy
    return
  end
  realwidth  = sprite.bitmap.width*sprite.zoom_x
  realheight = sprite.bitmap.height*sprite.zoom_y
  sprite.x = cx-(realwidth/2)
  sprite.y = cy-(realheight/2)
end

def showShadow?(species)
  metrics = load_data("Data/metrics.dat")
  return metrics[2][species]>0
end