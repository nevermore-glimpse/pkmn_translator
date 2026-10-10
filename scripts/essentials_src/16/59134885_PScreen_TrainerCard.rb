class PokemonTrainerCardScene
  def update
    pbUpdateSpriteHash(@sprites)
  end

  def pbStartScene
    @sprites={}
    @viewport=Viewport.new(0,0,Graphics.width,Graphics.height)
    @viewport.z=99999
    background=pbResolveBitmap(sprintf("Graphics/Pictures/trainercardbgf"))
    if $Trainer.isFemale? && background
      addBackgroundPlane(@sprites,"bg","trainercardbgf",@viewport)
    else
      addBackgroundPlane(@sprites,"bg","trainercardbg",@viewport)
    end
    cardexists=pbResolveBitmap(sprintf("Graphics/Pictures/trainercardf"))
    @sprites["card"]=IconSprite.new(0,0,@viewport)
    if $Trainer.isFemale? && cardexists
      @sprites["card"].setBitmap("Graphics/Pictures/trainercardf")
    else
      @sprites["card"].setBitmap("Graphics/Pictures/trainercard")
    end
    @sprites["overlay"]=BitmapSprite.new(Graphics.width,Graphics.height,@viewport)
    @sprites["trainer"]=IconSprite.new(336,112,@viewport)
    @sprites["trainer"].setBitmap(pbPlayerSpriteFile($Trainer.trainertype))
    @sprites["trainer"].x-=(@sprites["trainer"].bitmap.width-128)/2
    @sprites["trainer"].y-=(@sprites["trainer"].bitmap.height-128)
    @sprites["trainer"].z=2
    pbSetSystemFont(@sprites["overlay"].bitmap)
    pbDrawTrainerCardFront
    if $PokemonGlobal.trainerRecording
      $PokemonGlobal.trainerRecording.play
    end
    pbFadeInAndShow(@sprites) { update }
  end

  def pbDrawTrainerCardFront
    overlay=@sprites["overlay"].bitmap
    overlay.clear
    totalsec = Graphics.frame_count / Graphics.frame_rate
    hour = totalsec / 60 / 60
    min = totalsec / 60 % 60
    time=_ISPRINTF("{1:02d}:{2:02d}",hour,min)
    $PokemonGlobal.startTime=pbGetTimeNow if !$PokemonGlobal.startTime
    starttime=_ISPRINTF("{1:s} {2:d}, {3:d}",
       pbGetAbbrevMonthName($PokemonGlobal.startTime.mon),
       $PokemonGlobal.startTime.day,
       $PokemonGlobal.startTime.year)
    pubid=sprintf("%05d",$Trainer.publicID($Trainer.id))
    baseColor=Color.new(72,72,72)
    shadowColor=Color.new(160,160,160)
    textPositions=[
       [_INTL("Name"),34,64,0,baseColor,shadowColor],
       [_INTL("{1}",$Trainer.name),302,64,1,baseColor,shadowColor],
       [_INTL("ID No."),332,64,0,baseColor,shadowColor],
       [_INTL("{1}",pubid),468,64,1,baseColor,shadowColor],
       [_INTL("Money"),34,112,0,baseColor,shadowColor],
       [_INTL("${1}",$Trainer.money),302,112,1,baseColor,shadowColor],
       [_INTL("Pokédex"),34,160,0,baseColor,shadowColor],
       [_ISPRINTF("{1:d}/{2:d}",$Trainer.pokedexOwned,$Trainer.pokedexSeen),302,160,1,baseColor,shadowColor],
       [_INTL("Time"),34,208,0,baseColor,shadowColor],
       [time,302,208,1,baseColor,shadowColor],
       [_INTL("Started"),34,256,0,baseColor,shadowColor],
       [starttime,302,256,1,baseColor,shadowColor]
    ]
    pbDrawTextPositions(overlay,textPositions)
    x=72
    region=pbGetCurrentRegion(0) # Get the current region
    imagePositions=[]
    for i in 0...8
      if $Trainer.badges[i+region*8]
        imagePositions.push(["Graphics/Pictures/badges",x,310,i*32,region*32,32,32])
      end
      x+=48
    end
    pbDrawImagePositions(overlay,imagePositions)
  end

  def pbTrainerCard
    loop do
      Graphics.update
      Input.update
      self.update
      if Input.trigger?(Input::B)
        break
      end
    end 
  end

  def pbEndScene
    pbFadeOutAndHide(@sprites) { update }
    pbDisposeSpriteHash(@sprites)
    @viewport.dispose
  end
end



class PokemonTrainerCard
  def initialize(scene)
    @scene=scene
  end

  def pbStartScreen
    @scene.pbStartScene
    @scene.pbTrainerCard
    @scene.pbEndScene
  end
end