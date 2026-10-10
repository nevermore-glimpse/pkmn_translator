module Graphics
  @@transition=nil
  STOP_WHILE_TRANSITION = true

  unless defined?(transition_KGC_SpecialTransition)
    class << Graphics
      alias transition_KGC_SpecialTransition transition
    end

    class << Graphics
      alias update_KGC_SpecialTransition update
    end
  end

  def self.transition(duration = 8, filename = "", vague = 20)
    if judge_special_transition(duration,filename)
      duration = 0
      filename=""
    end
    begin
      transition_KGC_SpecialTransition(duration, filename, vague)
    rescue Exception
      if filename!=""
        transition_KGC_SpecialTransition(duration, "", vague)
      end
    end
    if STOP_WHILE_TRANSITION && !@_interrupt_transition
      while @@transition && !@@transition.disposed?
        update
      end
    end
  end

  def self.update
    update_KGC_SpecialTransition
=begin
    if Graphics.frame_count%40==0
      count=0
      ObjectSpace.each_object(Object) {|o|
         count+=1
      }
      echo("Objects: #{count}\r\n")
    end
=end
    if @@transition && !@@transition.disposed?
      @@transition.update
    end
    if @@transition && @@transition.disposed? 
      @@transition=nil
    end
  end

  def self.judge_special_transition(duration,filename)
    ret=true
    if @_interrupt_transition
      return false
    end
    if @@transition && !@@transition.disposed?
      @@transition.dispose
      @@transition=nil
    end
    dc=File.basename(filename).downcase
    if dc=="scrolldown"
      @@transition=ScrollScreen.new(duration,2)
    elsif dc=="scrollleft"
      @@transition=ScrollScreen.new(duration,4)
    elsif dc=="scrollright"
      @@transition=ScrollScreen.new(duration,6)
    elsif dc=="scrollup"
      @@transition=ScrollScreen.new(duration,8)
    elsif dc=="scrolldownleft"
      @@transition=ScrollScreen.new(duration,1)
    elsif dc=="scrolldownright"
      @@transition=ScrollScreen.new(duration,3)
    elsif dc=="scrollupleft"
      @@transition=ScrollScreen.new(duration,7)
    elsif dc=="scrollupright"
      @@transition=ScrollScreen.new(duration,9)
    elsif dc=="splash"
      @@transition=SplashTransition.new(duration)
    elsif dc=="random_stripe_v"
      @@transition=RandomStripeTransition.new(duration,0)
    elsif dc=="random_stripe_h"
      @@transition=RandomStripeTransition.new(duration,1)
    elsif dc=="rotatingpieces"
      @@transition=ShrinkingPieces.new(duration,true)
    elsif dc=="shrinkingpieces"
      @@transition=ShrinkingPieces.new(duration,false)
    elsif dc=="breakingglass"
      @@transition=BreakingGlass.new(duration)
    elsif dc=="mosaic"
      @@transition=MosaicTransition.new(duration)
    elsif dc=="zoomin"
      @@transition=ZoomInTransition.new(duration)
    elsif dc==""
      @@transition=FadeTransition.new(duration)
    else 
      ret=false
    end
    Graphics.frame_reset if ret
    return ret
  end
end



class BreakingGlass
  def initialize(numframes)
    @disposed=false
    @numframes=numframes
    @opacitychange=(numframes<=0) ? 255 : 255.0/numframes
    cx=6
    cy=5
    @bitmap=Graphics.snap_to_bitmap
    if !@bitmap
      @disposed=true
      return
    end
    width=@bitmap.width/cx
    height=@bitmap.height/cy
    @numtiles=cx*cy
    @viewport=Viewport.new(0,0,Graphics.width,Graphics.height)
    @viewport.z = 99999
    @sprites=[]
    @offset=[]
    @y=[]
    for i in 0...@numtiles
      @sprites[i]=Sprite.new(@viewport)
      @sprites[i].bitmap=@bitmap
      @sprites[i].x=width*(i%cx)
      @sprites[i].y=height*(i/cx)
      @sprites[i].src_rect.set(@sprites[i].x,@sprites[i].y,width,height)
      @offset[i]=(rand(100)+1)*3.0/100.0
      @y[i]=@sprites[i].y
    end
  end

  def disposed?
    @disposed
  end

  def dispose
    if !disposed?
      @bitmap.dispose
      for i in 0...@numtiles
        @sprites[i].visible=false
        @sprites[i].dispose
      end
      @sprites.clear
      @viewport.dispose if @viewport
      @disposed=true
    end
  end

  def update
    return if disposed?
    continue=false
    for i in 0...@numtiles
      @sprites[i].opacity-=@opacitychange
      @y[i]+=@offset[i]
      @sprites[i].y=@y[i]
      continue=true if @sprites[i].opacity>0
    end
    self.dispose if !continue
  end
end



class ShrinkingPieces
  def initialize(numframes,rotation)
    @disposed=false
    @rotation=rotation
    @numframes=numframes
    @opacitychange=(numframes<=0) ? 255 : 255.0/numframes
    cx=6
    cy=5
    @bitmap=Graphics.snap_to_bitmap
    if !@bitmap
      @disposed=true
      return
    end
    width=@bitmap.width/cx
    height=@bitmap.height/cy
    @numtiles=cx*cy
    @viewport=Viewport.new(0,0,Graphics.width,Graphics.height)
    @viewport.z = 99999
    @sprites=[]
    for i in 0...@numtiles
      @sprites[i]=Sprite.new(@viewport)
      @sprites[i].bitmap=@bitmap
      @sprites[i].ox=width/2
      @sprites[i].oy=height/2
      @sprites[i].x=width*(i%cx)+@sprites[i].ox
      @sprites[i].y=height*(i/cx)+@sprites[i].oy
      @sprites[i].src_rect.set(width*(i%cx),height*(i/cx),width,height)
    end
  end

  def disposed?
    @disposed
  end

  def dispose
    if !disposed?
      @bitmap.dispose
      for i in 0...@numtiles
        @sprites[i].visible=false
        @sprites[i].dispose
      end
      @sprites.clear
      @viewport.dispose if @viewport
      @disposed=true
    end
  end

  def update
    return if disposed?
    continue=false
    for i in 0...@numtiles
      @sprites[i].opacity-=@opacitychange
      if @rotation
        @sprites[i].angle+=40
        @sprites[i].angle%=360
      end
      @sprites[i].zoom_x=@sprites[i].opacity/255.0
      @sprites[i].zoom_y=@sprites[i].opacity/255.0
      continue=true if @sprites[i].opacity>0
    end
    self.dispose if !continue
  end
end



class SplashTransition
  SPLASH_SIZE=32

  def initialize(numframes,vague=9.6)
    @duration=numframes
    @numframes=numframes
    @splash_dir = []
    @disposed=false
    if @numframes<=0
      @disposed=true
      return
    end
    @buffer=Graphics.snap_to_bitmap
    if !@buffer
      @disposed=true
      return
    end
    @viewport=Viewport.new(0,0,Graphics.width,Graphics.height)
    @viewport.z = 99999
    @sprite=Sprite.new(@viewport)
    @sprite.bitmap = Bitmap.new(Graphics.width, Graphics.height)
    size = SPLASH_SIZE
    size = [size,1].max
    cells = Graphics.width*Graphics.height / (size ** 2)
    rows = Graphics.width / size
    rect = Rect.new(0, 0, size, size)
    mag = 40.0 / @numframes
    cells.times { |i|
       rect.x = i % rows * size
       rect.y = i / rows * size
       x = rect.x / size - (rows >> 1)
       y = rect.y / size - ((cells / rows) >> 1)
       r = Math.sqrt(x ** 2 + y ** 2) / vague
       @splash_dir[i] = []
       if r != 0
         @splash_dir[i][0] = x / r
         @splash_dir[i][1] = y / r
       else
         @splash_dir[i][0] = x != 0 ? (x * 1.5) : (pmrand * vague)
         @splash_dir[i][1] = y != 0 ? (y * 1.5) : (pmrand * vague)
       end
       @splash_dir[i][0] += (rand - 0.5) * vague
       @splash_dir[i][1] += (rand - 0.5) * vague
       @splash_dir[i][0] *= mag
       @splash_dir[i][1] *= mag
    }
    @sprite.bitmap.blt(0, 0,@buffer,@buffer.rect)
  end

  def disposed?; @disposed; end

  def dispose
    return if disposed?
    @buffer.dispose if @buffer
    @buffer=nil
    @sprite.visible=false
    @sprite.bitmap.dispose
    @sprite.dispose
    @viewport.dispose if @viewport
    @disposed=true
  end

  def update
    return if disposed?
    if @duration==0
      dispose
    else
      size = SPLASH_SIZE
      cells = Graphics.width*Graphics.height / (size ** 2)
      rows = Graphics.width / size
      rect = Rect.new(0, 0, size, size)
      buffer = @buffer
      sprite = @sprite
      phase = @numframes - @duration
      sprite.bitmap.clear
      cells.times { |i|
         rect.x = i % rows * size
         rect.y = i / rows * size
         dx = rect.x + @splash_dir[i][0] * phase
         dy = rect.y + @splash_dir[i][1] * phase
         sprite.bitmap.blt(dx, dy, buffer, rect)
      }
      sprite.opacity = 384 * @duration / @numframes
      @duration-=1
    end
  end

  private

  def pmrand
    return (rand(2) == 0 ? 1 : -1)
  end
end



class RandomStripeTransition
  RAND_STRIPE_SIZE=2

  def initialize(numframes,direction)
    @duration=numframes
    @numframes=numframes
    @disposed=false
    if @numframes<=0
      @disposed=true
      return
    end
    @buffer=Graphics.snap_to_bitmap
    if !@buffer
      @disposed=true
      return
    end
    @viewport=Viewport.new(0,0,Graphics.width,Graphics.height)
    @viewport.z = 99999
    @sprite = Sprite.new(@viewport)
    @sprite.bitmap = Bitmap.new(Graphics.width,Graphics.height)
    ########## 
    @direction=direction
    size = RAND_STRIPE_SIZE
    bands = (@direction == 0 ? Graphics.width : Graphics.height) / size
    @rand_stripe_deleted = []
    @rand_stripe_deleted_count = 0
    ary = (0...bands).to_a
    @rand_stripe_index_array = ary.sort_by { rand }
    ##########
    @sprite.bitmap.blt(0, 0, @buffer, @buffer.rect)
  end

  def disposed?; @disposed; end

  def dispose
    return if disposed?
    @buffer.dispose if @buffer
    @buffer=nil
    @sprite.visible=false
    @sprite.bitmap.dispose
    @sprite.dispose
    @viewport.dispose if @viewport
    @disposed=true
  end

  def update
    return if disposed?
    if @duration==0
      dispose
    else
      dir = @direction
      size = RAND_STRIPE_SIZE
      bands = (dir == 0 ? Graphics.width : Graphics.height) / size
      rect = Rect.new(0, 0, (dir == 0 ? size : Graphics.width), (dir == 0 ? Graphics.height : size))
      buffer = @buffer
      sprite = @sprite
      phase = @numframes - @duration
      count = (bands - bands * @duration / @numframes) - @rand_stripe_deleted_count
      while count > 0
        @rand_stripe_deleted[@rand_stripe_index_array.pop] = true
        @rand_stripe_deleted_count += 1
        count -= 1
      end
      sprite.bitmap.clear
      bands.to_i.times { |i|
         unless @rand_stripe_deleted[i]
           if dir == 0
             rect.x = i * size
             sprite.bitmap.blt(rect.x, 0, buffer, rect)
           else
             rect.y = i * size
             sprite.bitmap.blt(0, rect.y, buffer, rect)
           end
         end
      }
      @duration-=1
    end
  end
end



class ZoomInTransition
  def initialize(numframes)
    @duration=numframes
    @numframes=numframes
    @disposed=false
    if @numframes<=0
      @disposed=true
      return
    end
    @buffer=Graphics.snap_to_bitmap
    if !@buffer
      @disposed=true
      return
    end
    @width=@buffer.width
    @height=@buffer.height
    @viewport = Viewport.new(0,0,@width,@height)
    @viewport.z = 99999
    @sprite = Sprite.new(@viewport)
    @sprite.bitmap = @buffer
    @sprite.ox=@width/2
    @sprite.oy=@height/2
    @sprite.x=@width/2
    @sprite.y=@height/2
  end

  def disposed?; @disposed; end

  def dispose
    return if disposed?
    @buffer.dispose if @buffer
    @buffer=nil
    @sprite.dispose if @sprite
    @viewport.dispose if @viewport
    @disposed=true
  end

  def update
    return if disposed?
    if @duration==0
      dispose
    else
      @sprite.zoom_x+=0.2
      @sprite.zoom_y+=0.2
      @sprite.opacity=(@duration-1)*255/@numframes
      @duration-=1
    end
  end
end



class ScrollScreen
  def initialize(numframes,direction)
    @numframes=numframes
    @duration=numframes
    @dir=direction
    @disposed=false
    if @numframes<=0
      @disposed=true
      return
    end
    @buffer=Graphics.snap_to_bitmap
    if !@buffer
      @disposed=true
      return
    end
    @width=@buffer.width
    @height=@buffer.height
    @viewport = Viewport.new(0,0,@width,@height)
    @viewport.z = 99999
    @sprite = Sprite.new(@viewport)
    @sprite.bitmap = @buffer
  end

  def disposed?; @disposed; end

  def dispose
    return if disposed?
    @buffer.dispose if @buffer
    @buffer=nil
    @sprite.dispose if @sprite
    @viewport.dispose if @viewport
    @disposed=true
  end

  def update
    return if disposed?
    if @duration==0
      dispose
    else
      case @dir
      when 1 # down left
        @sprite.y+=(@height/@numframes)
        @sprite.x-=(@width/@numframes)
      when 2 # down
        @sprite.y+=(@height/@numframes)
      when 3 # down right
        @sprite.y+=(@height/@numframes)
        @sprite.x+=(@width/@numframes)
      when 4 # left
        @sprite.x-=(@width/@numframes)
      when 6 # right
        @sprite.x+=(@width/@numframes)
      when 7 # up left
        @sprite.y-=(@height/@numframes)
        @sprite.x-=(@width/@numframes)
      when 8 # up
        @sprite.y-=(@height/@numframes)
      when 9 # up right
        @sprite.y-=(@height/@numframes)
        @sprite.x+=(@width/@numframes)
      end
      @duration-=1
    end
  end
end



class MosaicTransition
  def initialize(numframes)
    @duration=numframes
    @numframes=numframes
    @disposed=false
    if @numframes<=0
      @disposed=true
      return
    end
    @buffer=Graphics.snap_to_bitmap
    if !@buffer
      @disposed=true
      return
    end
    @viewport = Viewport.new(0,0,Graphics.width,Graphics.height)
    @viewport.z = 99999
    @sprite = Sprite.new(@viewport)
    @sprite.bitmap = @buffer
    @bitmapclone=@buffer.clone
    @bitmapclone2=@buffer.clone
  end

  def disposed?; @disposed; end

  def dispose
    return if disposed?
    @buffer.dispose if @buffer
    @buffer=nil
    @sprite.dispose if @sprite
    @viewport.dispose if @viewport
    @disposed=true
  end

  def update
    return if disposed?
    if @duration==0
      dispose
    else
      @bitmapclone2.stretch_blt(
         Rect.new(0,0,@buffer.width*@duration/@numframes,
         @buffer.height*@duration/@numframes),@bitmapclone,
         Rect.new(0,0,@buffer.width,@buffer.height))
      @buffer.stretch_blt(
         Rect.new(0,0,@buffer.width,@buffer.height),@bitmapclone2,
         Rect.new(0,0,@buffer.width*@duration/@numframes,
         @buffer.height*@duration/@numframes))
      @duration-=1
    end
  end
end



class FadeTransition
  def initialize(numframes)
    @duration=numframes
    @numframes=numframes
    @disposed=false
    if @duration<=0
      @disposed=true
      return
    end
    @viewport = Viewport.new(0,0,Graphics.width,Graphics.height)
    @viewport.z = 99999
    @sprite = BitmapSprite.new(Graphics.width,Graphics.height,@viewport)
    @sprite.bitmap.fill_rect(0,0,Graphics.width,Graphics.height,Color.new(0,0,0))
    @sprite.opacity=0
  end

  def disposed?; @disposed; end

  def dispose
    return if disposed?
    @sprite.dispose if @sprite
    @viewport.dispose if @viewport
    @disposed=true
  end

  def update
    return if disposed?
    if @duration==0
      dispose
    else
      @sprite.opacity=(@duration-1)*255/@numframes
      @duration-=1
    end
  end
end