#===============================================================================
# PC menus
#===============================================================================
def pbPCItemStorage
  loop do
    command=Kernel.pbShowCommandsWithHelp(nil,
       [_INTL("Withdraw Item"),
       _INTL("Deposit Item"),
       _INTL("Toss Item"),
       _INTL("Exit")],
       [_INTL("Take out items from the PC."),
       _INTL("Store items in the PC."),
       _INTL("Throw away items stored in the PC."),
       _INTL("Go back to the previous menu.")],-1
    )
    if command==0 # Withdraw Item
      if !$PokemonGlobal.pcItemStorage
        $PokemonGlobal.pcItemStorage=PCItemStorage.new
      end
      if $PokemonGlobal.pcItemStorage.empty?
        Kernel.pbMessage(_INTL("There are no items."))
      else
        pbFadeOutIn(99999){
          scene = WithdrawItemScene.new
          screen = PokemonBagScreen.new(scene,$PokemonBag)
          ret = screen.pbWithdrawItemScreen
        }
      end
    elsif command==1 # Deposit Item
      pbFadeOutIn(99999){
        scene = PokemonBag_Scene.new
        screen = PokemonBagScreen.new(scene,$PokemonBag)
        ret = screen.pbDepositItemScreen
      }
    elsif command==2 # Toss Item
      if !$PokemonGlobal.pcItemStorage
        $PokemonGlobal.pcItemStorage=PCItemStorage.new
      end
      if $PokemonGlobal.pcItemStorage.empty?
        Kernel.pbMessage(_INTL("There are no items."))
      else
        pbFadeOutIn(99999){
          scene = TossItemScene.new
          screen = PokemonBagScreen.new(scene,$PokemonBag)
          ret = screen.pbTossItemScreen
        }
      end
    else
      break
    end
  end
end

def pbPCMailbox
  if !$PokemonGlobal.mailbox || $PokemonGlobal.mailbox.length==0
    Kernel.pbMessage(_INTL("There's no Mail here."))
  else
    loop do
      commands=[]
      for mail in $PokemonGlobal.mailbox
        commands.push(mail.sender)
      end
      commands.push(_INTL("Cancel"))
      command=Kernel.pbShowCommands(nil,commands,-1)
      if command>=0 && command<$PokemonGlobal.mailbox.length
        mailIndex=command
        command=Kernel.pbMessage(_INTL("What do you want to do with {1}'s Mail?",
           $PokemonGlobal.mailbox[mailIndex].sender),[
           _INTL("Read"),
           _INTL("Move to Bag"),
           _INTL("Give"),
           _INTL("Cancel")
           ],-1)
        if command==0 # Read
          pbFadeOutIn(99999){
            pbDisplayMail($PokemonGlobal.mailbox[mailIndex])
          }
        elsif command==1 # Move to Bag
          if Kernel.pbConfirmMessage(_INTL("The message will be lost. Is that OK?"))
            if $PokemonBag.pbStoreItem($PokemonGlobal.mailbox[mailIndex].item)
              Kernel.pbMessage(_INTL("The Mail was returned to the Bag with its message erased."))
              $PokemonGlobal.mailbox.delete_at(mailIndex)
            else
              Kernel.pbMessage(_INTL("The Bag is full."))
            end
          end
        elsif command==2 # Give
          pbFadeOutIn(99999){
            sscene = PokemonParty_Scene.new
            sscreen = PokemonPartyScreen.new(sscene,$Trainer.party)
            sscreen.pbPokemonGiveMailScreen(mailIndex)
          }
        end
      else
        break
      end
    end
  end
end

def pbTrainerPCMenu
  loop do
    command=Kernel.pbMessage(_INTL("What do you want to do?"),[
       _INTL("Item Storage"),
       _INTL("Mailbox"),
       _INTL("Turn Off")
       ],-1)
    if command==0
      pbPCItemStorage
    elsif command==1
      pbPCMailbox
    else
      break
    end
  end
end



class TrainerPC
  def shouldShow?
    return true
  end

  def name
    return _INTL("{1}'s PC",$Trainer.name)
  end

  def access
    Kernel.pbMessage(_INTL("\\se[PC access]Accessed {1}'s PC.",$Trainer.name))
    pbTrainerPCMenu
  end
end



def Kernel.pbGetStorageCreator
  creator=pbStorageCreator
  creator=_INTL("Bill") if !creator || creator==""
  return creator
end



class StorageSystemPC
  def shouldShow?
    return true
  end

  def name
    if $PokemonGlobal.seenStorageCreator
      return _INTL("{1}'s PC",Kernel.pbGetStorageCreator)
    else
      return _INTL("Someone's PC")
    end
  end

  def access
    Kernel.pbMessage(_INTL("\\se[PC access]The Pokémon Storage System was opened."))
    loop do
      command=Kernel.pbShowCommandsWithHelp(nil,
         [_INTL("Organize Boxes"),
         _INTL("Withdraw Pokémon"),
         _INTL("Deposit Pokémon"),
         _INTL("See ya!")],
         [_INTL("Organize the Pokémon in Boxes and in your party."),
         _INTL("Move Pokémon stored in Boxes to your party."),
         _INTL("Store Pokémon in your party in Boxes."),
         _INTL("Return to the previous menu.")],-1
      )
      if command>=0 && command<3
        if command==1   # Withdraw
          if $PokemonStorage.party.length>=6
            Kernel.pbMessage(_INTL("Your party is full!"))
            next
          end
        elsif command==2   # Deposit
          count=0
          for p in $PokemonStorage.party
            count+=1 if p && !p.egg? && p.hp>0
          end
          if count<=1
            Kernel.pbMessage(_INTL("Can't deposit the last Pokémon!"))
            next
          end
        end
        pbFadeOutIn(99999){
          scene = PokemonStorageScene.new
          screen = PokemonStorageScreen.new(scene,$PokemonStorage)
          screen.pbStartScreen(command)
        }
      else
        break
      end
    end
  end
end



def pbTrainerPC
  Kernel.pbMessage(_INTL("\\se[PC open]{1} booted up the PC.",$Trainer.name))
  pbTrainerPCMenu
  pbSEPlay("PC close")
end

def pbPokeCenterPC
  Kernel.pbMessage(_INTL("\\se[PC open]{1} booted up the PC.",$Trainer.name))
  loop do
    commands=PokemonPCList.getCommandList
    command=Kernel.pbMessage(_INTL("Which PC should be accessed?"),commands,commands.length)
    break if !PokemonPCList.callCommand(command)
  end
  pbSEPlay("PC close")
end



module PokemonPCList
  @@pclist=[]

  def self.registerPC(pc)
    @@pclist.push(pc)
  end

  def self.getCommandList()
    commands=[]
    for pc in @@pclist
      if pc.shouldShow?
        commands.push(pc.name)
      end
    end
    commands.push(_INTL("Log Off"))
    return commands
  end

  def self.callCommand(cmd)
    if cmd<0 || cmd>=@@pclist.length
      return false
    end
    i=0
    for pc in @@pclist
      if pc.shouldShow?
        if i==cmd
           pc.access()
           return true
        end
        i+=1
      end
    end
    return false
  end
end



PokemonPCList.registerPC(StorageSystemPC.new)
PokemonPCList.registerPC(TrainerPC.new)