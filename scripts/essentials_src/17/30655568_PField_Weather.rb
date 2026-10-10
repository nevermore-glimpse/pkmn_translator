begin
  module PBFieldWeather
    None        = 0 # None must be 0 (preset RMXP weather)
    Rain        = 1 # Rain must be 1 (preset RMXP weather)
    Storm       = 2 # Storm must be 2 (preset RMXP weather)
    Snow        = 3 # Snow must be 3 (preset RMXP weather)
    Blizzard    = 4
    Sandstorm   = 5
    HeavyRain   = 6
    Sun = Sunny = 7

    def PBFieldWeather.maxValue; 7; end
  end

rescue Exception
  if $!.is_a?(SystemExit) || "#{$!.class}"=="Reset"
    raise $!
  end
end



module RPG
  class Weather
    attr_reader :type
    attr_reader :max
    attr_reader :ox
    attr_reader :oy

    def prepareSandstormBitmaps
      if !@sandstormBitmap1
        bmwidth  = 200
        bmheight = 200
        @sandstormBitmap1 = Bitmap.new(bmwidth,bmheight)
        @sandstormBitmap2 = Bitmap.new(bmwidth,bmheight)
        sandstormColors = [
           Color.new(31*8,28*8,17*8),
           Color.new(23*8,16*8,9*8),
           Color.new(29*8,24*8,15*8),
           Color.new(26*8,20*8,12*8),
           Color.new(20*8,13*8,6*8),
           Color.new(31*8,30*8,20*8),
           Color.new(27*8,25*8,20*8)
        ]
        for i in 0..540
          @sandstormBitmap1.fill_rect(rand(bmwidth/2)*2,rand(bmheight/2)*2,2,2,sandstormColors[rand(7)])
          @sandstormBitmap2.fill_rect(rand(bmwidth/2)*2,rand(bmheight/2)*2,2,2,sandstormColors[rand(7)])
        end
        @weatherTypes[PBFieldWeather::Sandstorm][0][0] = @sandstormBitmap1
        @weatherTypes[PBFieldWeather::Sandstorm][0][1] = @sandstormBitmap2
      end
    end

    def prepareSnowBitmaps
      if !@snowBitmap1
        bmwidth  = 10
        bmheight = 10
        @snowBitmap1 = Bitmap.new(bmwidth,bmheight)
        @snowBitmap2 = Bitmap.new(bmwidth,bmheight)
        @snowBitmap3 = Bitmap.new(bmwidth,bmheight)
        snowcolor = Color.new(224, 232, 240, 255)
        @snowBitmap1.fill_rect(4,2,2,2,snowcolor)
        @snowBitmap1.fill_rect(2,4,6,2,snowcolor)
        @snowBitmap1.fill_rect(4,6,2,2,snowcolor)
        @snowBitmap2.fill_rect(2,0,4,2,snowcolor)
        @snowBitmap2.fill_rect(0,2,8,4,snowcolor)
        @snowBitmap2.fill_rect(2,6,4,2,snowcolor)
        @snowBitmap3.fill_rect(4,0,2,2,snowcolor)
        @snowBitmap3.fill_rect(2,2,6,2,snowcolor)
        @snowBitmap3.fill_rect(0,4,10,2,snowcolor)
        @snowBitmap3.fill_rect(2,6,6,2,snowcolor)
        @snowBitmap3.fill_rect(4,8,2,2,snowcolor)
        @weatherTypes[PBFieldWeather::Snow][0][0] = @snowBitmap1
        @weatherTypes[PBFieldWeather::Snow][0][1] = @snowBitmap2
        @weatherTypes[PBFieldWeather::Snow][0][2] = @snowBitmap3
      end
    end

    def prepareBlizzardBitmaps
      if !@blizzardBitmap1
        bmwidth = 10; bmheight = 10
        @blizzardBitmap1 = Bitmap.new(bmwidth,bmheight)
        @blizzardBitmap2 = Bitmap.new(bmwidth,bmheight)
        bmwidth = 200; bmheight = 200
        @blizzardBitmap3 = Bitmap.new(bmwidth,bmheight)
        @blizzardBitmap4 = Bitmap.new(bmwidth,bmheight)
        snowcolor = Color.new(224,232,240,255)
        @blizzardBitmap1.fill_rect(2,0,4,2,snowcolor)
        @blizzardBitmap1.fill_rect(0,2,8,4,snowcolor)
        @blizzardBitmap1.fill_rect(2,6,4,2,snowcolor)
        @blizzardBitmap2.fill_rect(4,0,2,2,snowcolor)
        @blizzardBitmap2.fill_rect(2,2,6,2,snowcolor)
        @blizzardBitmap2.fill_rect(0,4,10,2,snowcolor)
        @blizzardBitmap2.fill_rect(2,6,6,2,snowcolor)
        @blizzardBitmap2.fill_rect(4,8,2,2,snowcolor)
        for i in 0..540
          @blizzardBitmap3.fill_rect(rand(bmwidth/2)*2,rand(bmheight/2)*2,2,2,snowcolor)
          @blizzardBitmap4.fill_rect(rand(bmwidth/2)*2,rand(bmheight/2)*2,2,2,snowcolor)
        end
        @weatherTypes[PBFieldWeather::Blizzard][0][0] = @blizzardBitmap1
        @weatherTypes[PBFieldWeather::Blizzard][0][1] = @blizzardBitmap2
        @weatherTypes[PBFieldWeather::Blizzard][0][2] = @blizzardBitmap3 # Tripled to make them 3x as common
        @weatherTypes[PBFieldWeather::Blizzard][0][3] = @blizzardBitmap3
        @weatherTypes[PBFieldWeather::Blizzard][0][4] = @blizzardBitmap3
        @weatherTypes[PBFieldWeather::Blizzard][0][5] = @blizzardBitmap4 # Tripled to make them 3x as common
        @weatherTypes[PBFieldWeather::Blizzard][0][6] = @blizzardBitmap4
        @weatherTypes[PBFieldWeather::Blizzard][0][7] = @blizzardBitmap4
      end
    end

    def initialize(viewport = nil)
      @type = 0
      @max = 0
      @ox = 0
      @oy = 0
      @sunvalue = 0
      @sun = 0
      @viewport = Viewport.new(0,0,Graphics.width,Graphics.height)
      @viewport.z = viewport.z+1
      @origviewport = viewport
      color = Color.new(255,255,255,255)
      @rain_bitmap = Bitmap.new(32,128)
      for i in 0...16
        @rain_bitmap.fill_rect(30-(i*2),i*8,2,8,color)
      end
      @storm_bitmap = Bitmap.new(192,192)
      for i in 0...96
        @storm_bitmap.fill_rect(190-(i*2),i*2,2,2,color)
      end
      @weatherTypes = []
      @weatherTypes[PBFieldWeather::None]      = nil
      @weatherTypes[PBFieldWeather::Rain]      = [[@rain_bitmap],-6,24,-8]
      @weatherTypes[PBFieldWeather::HeavyRain] = [[@storm_bitmap],-24,24,-4]
      @weatherTypes[PBFieldWeather::Storm]     = [[@storm_bitmap],-24,24,-4]
      @weatherTypes[PBFieldWeather::Snow]      = [[],-4,8,0]
      @weatherTypes[PBFieldWeather::Blizzard]  = [[],-16,16,-4]
      @weatherTypes[PBFieldWeather::Sandstorm] = [[],-12,4,-2]
      @weatherTypes[PBFieldWeather::Sun]       = nil
      @sprites = []
    end

    def ensureSprites
      return if @sprites.length>=40
      for i in 1..40
        sprite = Sprite.new(@origviewport)
        sprite.z       = 1000
        sprite.ox      = @ox
        sprite.oy      = @oy
        sprite.opacity = 0
        sprite.visible = (i<=@max)
        @sprites.push(sprite)
      end
    end

    def dispose
      for sprite in @sprites
        sprite.dispose
      end
      @viewport.dispose
      for weather in @weatherTypes
        next if !weather
        for bm in weather[0]
          bm.dispose
        end
      end
    end

    def type=(type)
      return if @type==type
      @type = type
      case @type
      when PBFieldWeather::Rain
        bitmap = @rain_bitmap
      when PBFieldWeather::HeavyRain, PBFieldWeather::Storm
        bitmap = @storm_bitmap
      when PBFieldWeather::Snow
        prepareSnowBitmaps
      when PBFieldWeather::Blizzard
        prepareBlizzardBitmaps
      when PBFieldWeather::Sandstorm
        prepareSandstormBitmaps
      else
        bitmap = nil
      end
      if @type==PBFieldWeather::None
        for sprite in @sprites
          sprite.dispose
        end
        @sprites.clear
        return
      end
      weatherbitmaps = (@type==PBFieldWeather::None || @type==PBFieldWeather::Sun) ? nil : @weatherTypes[@type][0]
      ensureSprites
      for i in 1..40
        sprite = @sprites[i]
        if sprite!=nil
          if @type==PBFieldWeather::Blizzard || @type==PBFieldWeather::Sandstorm
            sprite.mirror = (rand(2)==0)
          else
            sprite.mirror = false
          end
          sprite.visible = (i<=@max)
          sprite.bitmap  = (@type==PBFieldWeather::None || @type==PBFieldWeather::Sun) ? nil : weatherbitmaps[i%weatherbitmaps.length]
        end
      end
    end

    def ox=(ox)
      return if @ox==ox
      @ox = ox
      for sprite in @sprites
        sprite.ox = @ox
      end
    end

    def oy=(oy)
      return if @oy==oy
      @oy = oy
      for sprite in @sprites
        sprite.oy = @oy
      end
    end

    def max=(max)
      return if @max==max
      @max = [[max,0].max,40].min
      if @max==0
        for sprite in @sprites
          sprite.dispose
        end
        @sprites.clear
      else
        for i in 1..40
          sprite = @sprites[i]
          if sprite!=nil
            sprite.visible = (i<=@max)
          end
        end
      end
    end

    def update
      # @max is (power+1)*4, where power is between 1 and 9
      case @type
      when PBFieldWeather::None
        @viewport.tone.set(0,0,0,0)
      when PBFieldWeather::Rain
        @viewport.tone.set(-@max*3/4,-@max*3/4,-@max*3/4,10)
      when PBFieldWeather::HeavyRain, PBFieldWeather::Storm
        @viewport.tone.set(-@max*6/4,-@max*6/4,-@max*6/4,20)
      when PBFieldWeather::Snow
        @viewport.tone.set(@max*2/4,@max*2/4,@max*2/4,0)
      when PBFieldWeather::Blizzard
        @viewport.tone.set(@max*3/4,@max*3/4,@max*3/4,0)
      when PBFieldWeather::Sandstorm
        @viewport.tone.set(@max*2/4,0,-@max*2/4,0)
      when PBFieldWeather::Sun
        unless @sun==@max || @sun==-@max
          @sun = @max
        end
        @sun = -@sun if @sunvalue>@max || @sunvalue<0
        @sunvalue = @sunvalue+@sun/32
        @viewport.tone.set(@sunvalue+63,@sunvalue+63,@sunvalue/2+31,0)
      end
      # Storm flashes
      if @type==PBFieldWeather::Storm
        rnd = rand(300)
        if rnd<4
          @viewport.flash(Color.new(255,255,255,230),rnd*20)
        end
      end
      @viewport.update
      return if @type==PBFieldWeather::None || @type==PBFieldWeather::Sun
      ensureSprites
      for i in 1..@max
        sprite = @sprites[i]
        break if sprite==nil
        sprite.x += @weatherTypes[@type][1]
        sprite.x += [2,0,0,-2][rand(4)] if @type==PBFieldWeather::Snow || @type==PBFieldWeather::Blizzard
        sprite.y += @weatherTypes[@type][2]
        sprite.opacity += @weatherTypes[@type][3]
        x = sprite.x-@ox
        y = sprite.y-@oy
        nomwidth  = Graphics.width
        nomheight = Graphics.height
        if sprite.opacity<64 || x<-50 || x>nomwidth+128 || y<-300 || y>nomheight+20
          sprite.x = rand(nomwidth+150)-50+@ox
          sprite.y = rand(nomheight+150)-200+@oy
          sprite.opacity = 255
          if @type==PBFieldWeather::Blizzard || @type==PBFieldWeather::Sandstorm
            sprite.mirror = (rand(2)==0)
          else
            sprite.mirror = false
          end
        end
        pbDayNightTint(sprite)
      end
    end
  end
end