class PokemonTrade_Scene
  def pbUpdate
    pbUpdateSpriteHash(@sprites)
  end

  def pbRunPictures(pictures,sprites)
    loop do
      for i in 0...pictures.length
        pictures[i].update
      end
      for i in 0...sprites.length
        if sprites[i].is_a?(IconSprite)
          setPictureIconSprite(sprites[i],pictures[i])
        else
          setPictureSprite(sprites[i],pictures[i])
        end
      end
      Graphics.update
      Input.update
      running=false
      for i in 0...pictures.length
        running=true if pictures[i].running?
      end
      break if !running
    end
  end

  def pbStartScreen(pokemon,pokemon2,trader1,trader2)
    @sprites={}
    @viewport=Viewport.new(0,0,Graphics.width,Graphics.height)
    @viewport.z=99999
    @pokemon=pokemon
    @pokemon2=pokemon2
    @trader1=trader1
    @trader2=trader2
    metrics=load_data("Data/metrics.dat")
    addBackgroundOrColoredPlane(@sprites,"background","tradebg",
       Color.new(248,248,248),@viewport)
    @sprites["rsprite1"]=PokemonSprite.new(@viewport)
    @sprites["rsprite1"].setPokemonBitmap(@pokemon,false)
    @sprites["rsprite1"].setOffset(PictureOrigin::Bottom)
    @sprites["rsprite1"].x=Graphics.width/2
    @sprites["rsprite1"].y = 264
    @sprites["rsprite1"].y += (metrics[1][@pokemon.species] || 0)*2 - (metrics[2][@pokemon.species] || 0)*2
    @sprites["rsprite2"]=PokemonSprite.new(@viewport)
    @sprites["rsprite2"].setPokemonBitmap(@pokemon2,false)
    @sprites["rsprite2"].setOffset(PictureOrigin::Bottom)
    @sprites["rsprite2"].x=Graphics.width/2
    @sprites["rsprite2"].y = 264
    @sprites["rsprite2"].y += (metrics[1][@pokemon2.species] || 0)*2 - (metrics[2][@pokemon2.species] || 0)*2
    @sprites["rsprite2"].visible=false
    @sprites["msgwindow"]=Kernel.pbCreateMessageWindow(@viewport)
    pbFadeInAndShow(@sprites)
  end

  def pbScene1
    spriteBall=IconSprite.new(0,0,@viewport)
    pictureBall=PictureEx.new(0)
    picturePoke=PictureEx.new(0)
    # Starting position of ball
    pictureBall.moveVisible(1,true)
    pictureBall.moveName(1,sprintf("Graphics/Pictures/Battle/ball_%02d",@pokemon.ballused))
    pictureBall.moveOrigin(1,PictureOrigin::Center)
    pictureBall.moveXY(0,1,Graphics.width/2,48)
    # Starting position of sprite
    picturePoke.moveVisible(1,true)
    picturePoke.moveOrigin(1,PictureOrigin::Bottom)
    picturePoke.moveXY(0,1,@sprites["rsprite1"].x,@sprites["rsprite1"].y)
    # Change sprite color
    delay=picturePoke.totalDuration+4
    picturePoke.moveColor(10,delay,Color.new(31*8,22*8,30*8,255))
    # Recall
    delay=picturePoke.totalDuration
    picturePoke.moveSE(delay,"Audio/SE/Battle recall")
    pictureBall.moveName(delay,sprintf("Graphics/Pictures/Battle/ball_%02d_open",@pokemon.ballused))
    # Move sprite to ball
    picturePoke.moveZoom(15,delay,0)
    picturePoke.moveXY(15,delay,Graphics.width/2,48)
    picturePoke.moveSE(delay+10,"Audio/SE/Battle jump to ball")
    picturePoke.moveVisible(delay+15,false)
    pictureBall.moveName(picturePoke.totalDuration+2,sprintf("Graphics/Pictures/Battle/ball_%02d",@pokemon.ballused))
    delay=picturePoke.totalDuration+20
    pictureBall.moveXY(12,delay,Graphics.width/2,-32)
    pbRunPictures(
       [picturePoke,pictureBall],
       [@sprites["rsprite1"],spriteBall]
    )
    spriteBall.dispose
  end

  def pbScene2
    spriteBall=IconSprite.new(0,0,@viewport)
    pictureBall=PictureEx.new(0)
    picturePoke=PictureEx.new(0)
    # Starting position of ball
    pictureBall.moveVisible(1,true)
    pictureBall.moveName(1,sprintf("Graphics/Pictures/Battle/ball_%02d",@pokemon2.ballused))
    pictureBall.moveOrigin(1,PictureOrigin::Center)
    pictureBall.moveXY(0,1,Graphics.width/2,-32)
    # Starting position of sprite
    picturePoke.moveVisible(1,false)
    picturePoke.moveOrigin(1,PictureOrigin::Bottom)
    picturePoke.moveZoom(0,1,0)
    picturePoke.moveColor(0,1,Color.new(31*8,22*8,30*8,255))
    # Dropping ball
    y=Graphics.height-96-16-16
    delay=picturePoke.totalDuration+4
    pictureBall.moveXY(15,delay,Graphics.width/2,y)
    pictureBall.moveSE(pictureBall.totalDuration,"Audio/SE/Battle ball drop")
    pictureBall.moveXY(8,pictureBall.totalDuration+2,Graphics.width/2,y-60)
    pictureBall.moveXY(7,pictureBall.totalDuration+2,Graphics.width/2,y)
    pictureBall.moveSE(pictureBall.totalDuration,"Audio/SE/Battle ball drop")
    pictureBall.moveXY(6,pictureBall.totalDuration+2,Graphics.width/2,y-40)
    pictureBall.moveXY(5,pictureBall.totalDuration+2,Graphics.width/2,y)
    pictureBall.moveSE(pictureBall.totalDuration,"Audio/SE/Battle ball drop")
    pictureBall.moveXY(4,pictureBall.totalDuration+2,Graphics.width/2,y-20)
    pictureBall.moveXY(3,pictureBall.totalDuration+2,Graphics.width/2,y)
    pictureBall.moveSE(pictureBall.totalDuration,"Audio/SE/Battle ball drop")
    picturePoke.moveXY(0,pictureBall.totalDuration,Graphics.width/2,y)
    delay=pictureBall.totalDuration+18
    picturePoke.moveSE(delay,"Audio/SE/Battle recall")
    cry=pbResolveAudioSE(pbCryFile(@pokemon2))
    picturePoke.moveSE(delay,cry) if cry
    pictureBall.moveName(delay,sprintf("Graphics/Pictures/Battle/ball_%02d_open",@pokemon2.ballused))
    pictureBall.moveVisible(delay+10,false)
    picturePoke.moveVisible(delay,true)
    picturePoke.moveZoom(15,delay,100)
    picturePoke.moveXY(15,delay,Graphics.width/2,@sprites["rsprite2"].y)
    delay=picturePoke.totalDuration
    picturePoke.moveColor(10,delay,Color.new(31*8,22*8,30*8,0))
    pbRunPictures(
       [picturePoke,pictureBall],
       [@sprites["rsprite2"],spriteBall]
    )
    spriteBall.dispose
  end

  def pbEndScreen
    Kernel.pbDisposeMessageWindow(@sprites["msgwindow"])
    pbFadeOutAndHide(@sprites)
    pbDisposeSpriteHash(@sprites)
    @viewport.dispose
    newspecies=pbTradeCheckEvolution(@pokemon2,@pokemon)
    if newspecies>0
      evo=PokemonEvolutionScene.new
      evo.pbStartScreen(@pokemon2,newspecies)
      evo.pbEvolution(false)
      evo.pbEndScreen
    end
  end

  def pbTrade
    pbBGMStop
    pbPlayCry(@pokemon)
    speciesname1=PBSpecies.getName(@pokemon.species)
    speciesname2=PBSpecies.getName(@pokemon2.species)
    Kernel.pbMessageDisplay(@sprites["msgwindow"],
       _ISPRINTF("{1:s}\r\nID: {2:05d}   OT: {3:s}\\wtnp[0]",
       @pokemon.name,@pokemon.publicID,@pokemon.ot)) { pbUpdate }
    Kernel.pbMessageWaitForInput(@sprites["msgwindow"],100,true) { pbUpdate }
    pbPlayDecisionSE
    pbScene1
    Kernel.pbMessageDisplay(@sprites["msgwindow"],
       _INTL("For {1}'s {2},\r\n{3} sends {4}.\1",@trader1,speciesname1,@trader2,speciesname2)) { pbUpdate }
    Kernel.pbMessageDisplay(@sprites["msgwindow"],
       _INTL("{1} bids farewell to {2}.",@trader2,speciesname2)) { pbUpdate }
    pbScene2
    Kernel.pbMessageDisplay(@sprites["msgwindow"],
       _ISPRINTF("{1:s}\r\nID: {2:05d}   OT: {3:s}\1",
       @pokemon2.name,@pokemon2.publicID,@pokemon2.ot)) { pbUpdate }
    Kernel.pbMessageDisplay(@sprites["msgwindow"],
       _INTL("Take good care of {1}.",speciesname2)) { pbUpdate }
  end
end



def pbStartTrade(pokemonIndex,newpoke,nickname,trainerName,trainerGender=0)
  myPokemon=$Trainer.party[pokemonIndex]
  opponent=PokeBattle_Trainer.new(trainerName,trainerGender)
  opponent.setForeignID($Trainer)
  yourPokemon=nil; resetmoves=true
  if newpoke.is_a?(PokeBattle_Pokemon)
    newpoke.trainerID=opponent.id
    newpoke.ot=opponent.name
    newpoke.otgender=opponent.gender
    newpoke.language=opponent.language
    yourPokemon=newpoke
    resetmoves=false
  else
    if newpoke.is_a?(String) || newpoke.is_a?(Symbol)
      raise _INTL("Species does not exist ({1}).",newpoke) if !hasConst?(PBSpecies,newpoke)
      newpoke=getID(PBSpecies,newpoke)
    end
    yourPokemon=PokeBattle_Pokemon.new(newpoke,myPokemon.level,opponent)
  end
  yourPokemon.name=nickname
  yourPokemon.obtainMode=2 # traded
  yourPokemon.resetMoves if resetmoves
  yourPokemon.pbRecordFirstMoves
  $Trainer.seen[yourPokemon.species]=true
  $Trainer.owned[yourPokemon.species]=true
  pbSeenForm(yourPokemon)
  pbFadeOutInWithMusic(99999){
    evo=PokemonTrade_Scene.new
    evo.pbStartScreen(myPokemon,yourPokemon,$Trainer.name,opponent.name)
    evo.pbTrade
    evo.pbEndScreen
  }
  $Trainer.party[pokemonIndex]=yourPokemon
end

#===============================================================================
# Evolution methods
#===============================================================================
def pbTradeCheckEvolution(pokemon,pokemon2)
  ret=pbCheckEvolutionEx(pokemon){|pokemon,evonib,level,poke|
    case evonib
    when PBEvolution::Trade
      next poke
    when PBEvolution::TradeItem
      if pokemon.item==level
        pokemon.setItem(0)
        next poke
      end
    when PBEvolution::TradeSpecies
      next poke if pokemon2.species==level
    end
    next -1
  }
  return ret
end