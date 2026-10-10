#===============================================================================
# The Bag object, which actually contains all the items
#===============================================================================
class PokemonBag
  attr_accessor :lastpocket
  attr_reader :pockets

  def self.pocketNames
    return pbPocketNames
  end

  def self.numPockets
    return self.pocketNames.length-1
  end

  def initialize
    @lastpocket = 1
    @pockets    = []
    @choices    = []
    for i in 0..PokemonBag.numPockets
      @pockets[i] = []
      @choices[i] = 0
    end
    @registeredItems = []
    @registeredIndex = [0,0,1]
  end

  def rearrange
    if (@pockets.length-1)!=PokemonBag.numPockets
      newpockets = []
      for i in 0..PokemonBag.numPockets
        newpockets[i] = []
        @choices[i]   = 0 if !@choices[i]
      end
      nump = PokemonBag.numPockets
      for i in 0...[@pockets.length,nump].min
        for item in @pockets[i]
          p = pbGetPocket(item[0])
          newpockets[p].push(item)
        end
      end
      @pockets = newpockets
    end
  end

  def clear
    for pocket in @pockets
      pocket.clear
    end
  end

  def pockets
    rearrange
    return @pockets
  end

  def maxPocketSize(pocket)
    maxsize = MAXPOCKETSIZE[pocket]
    return -1 if !maxsize
    return maxsize
  end

  # Gets the index of the current selected item in the pocket
  def getChoice(pocket)
    if pocket<=0 || pocket>PokemonBag.numPockets
      raise ArgumentError.new(_INTL("Invalid pocket: {1}",pocket.inspect))
    end
    rearrange
    return [@choices[pocket],@pockets[pocket].length].min || 0
  end

  # Sets the index of the current selected item in the pocket
  def setChoice(pocket,value)
    if pocket<=0 || pocket>PokemonBag.numPockets
      raise ArgumentError.new(_INTL("Invalid pocket: {1}",pocket.inspect))
    end
    rearrange
    @choices[pocket] = value if value<=@pockets[pocket].length
  end

  def getAllChoices
    ret = @choices.clone
    for i in 0...@choices.length; @choices[i] = 0; end
    return ret
  end

  def setAllChoices(choices)
    @choices = choices
  end

  def pbQuantity(item)
    if item.is_a?(String) || item.is_a?(Symbol)
      item = getID(PBItems,item)
    end
    if !item || item<1
      raise ArgumentError.new(_INTL("Item number {1} is invalid.",item))
      return 0
    end
    pocket = pbGetPocket(item)
    maxsize = maxPocketSize(pocket)
    maxsize = @pockets[pocket].length if maxsize<0
    return ItemStorageHelper.pbQuantity(@pockets[pocket],maxsize,item)
  end

  def pbHasItem?(item)
    return pbQuantity(item)>0
  end

  def pbCanStore?(item,qty=1)
    if item.is_a?(String) || item.is_a?(Symbol)
      item = getID(PBItems,item)
    end
    if !item || item<1
      raise ArgumentError.new(_INTL("Item number {1} is invalid.",item))
      return false
    end
    pocket = pbGetPocket(item)
    maxsize = maxPocketSize(pocket)
    maxsize = @pockets[pocket].length+1 if maxsize<0
    return ItemStorageHelper.pbCanStore?(@pockets[pocket],maxsize,BAGMAXPERSLOT,item,qty)
  end

  def pbStoreAllOrNone(item,qty=1)
    if item.is_a?(String) || item.is_a?(Symbol)
      item = getID(PBItems,item)
    end
    if !item || item<1
      raise ArgumentError.new(_INTL("Item number {1} is invalid.",item))
      return false
    end
    pocket = pbGetPocket(item)
    maxsize = maxPocketSize(pocket)
    maxsize = @pockets[pocket].length+1 if maxsize<0
    return ItemStorageHelper.pbStoreAllOrNone(@pockets[pocket],maxsize,BAGMAXPERSLOT,item,qty)
  end

  def pbStoreItem(item,qty=1)
    if item.is_a?(String) || item.is_a?(Symbol)
      item = getID(PBItems,item)
    end
    if !item || item<1
      raise ArgumentError.new(_INTL("Item number {1} is invalid.",item))
      return false
    end
    pocket = pbGetPocket(item)
    maxsize = maxPocketSize(pocket)
    maxsize = @pockets[pocket].length+1 if maxsize<0
    return ItemStorageHelper.pbStoreItem(@pockets[pocket],maxsize,BAGMAXPERSLOT,item,qty,true)
  end

  def pbChangeItem(olditem,newitem)
    if olditem.is_a?(String) || olditem.is_a?(Symbol)
      olditem = getID(PBItems,olditem)
    end
    if newitem.is_a?(String) || newitem.is_a?(Symbol)
      newitem = getID(PBItems,newitem)
    end
    if !olditem || olditem<1
      raise ArgumentError.new(_INTL("Item number {1} is invalid.",olditem))
      return false
    elsif !newitem || newitem<1
      raise ArgumentError.new(_INTL("Item number {1} is invalid.",newitem))
      return false
    end
    pocket = pbGetPocket(olditem)
    maxsize = maxPocketSize(pocket)
    maxsize = @pockets[pocket].length if maxsize<0
    ret = false
    for i in 0...maxsize
      itemslot = @pockets[pocket][i]
      if itemslot && itemslot[0]==olditem
        itemslot[0] = newitem
        ret = true
      end
    end
    return ret
  end

  def pbChangeQuantity(pocket,index,newqty=1)
    return false if pocket<=0 || pocket>self.numPockets
    return false if @pockets[pocket].length<index
    newqty = [newqty,maxPocketSize(pocket)].min
    @pockets[pocket][index][1] = newqty
    return true
  end

  def pbDeleteItem(item,qty=1)
    if item.is_a?(String) || item.is_a?(Symbol)
      item = getID(PBItems,item)
    end
    if !item || item<1
      raise ArgumentError.new(_INTL("Item number {1} is invalid.",item))
      return false
    end
    pocket = pbGetPocket(item)
    maxsize = maxPocketSize(pocket)
    maxsize = @pockets[pocket].length if maxsize<0
    ret = ItemStorageHelper.pbDeleteItem(@pockets[pocket],maxsize,item,qty)
    return ret
  end

  def registeredItems
    @registeredItems = [] if !@registeredItems
    if @registeredItem && @registeredItem>0 && !@registeredItems.include?(@registeredItem)
      @registeredItems.push(@registeredItem)
      @registeredItem = nil
    end
    return @registeredItems
  end

  def registeredItem; redisteredItems; end

  def pbIsRegistered?(item)
    registeredlist = self.registeredItems
    return registeredlist.include?(item)
  end

  # Registers the item in the Ready Menu.
  def pbRegisterItem(item)
    if item.is_a?(String) || item.is_a?(Symbol)
      item = getID(PBItems,item)
    end
    if !item || item<1
      raise ArgumentError.new(_INTL("Item number {1} is invalid.",item))
      return
    end
    registeredlist = self.registeredItems
    registeredlist.push(item) if !registeredlist.include?(item)
  end

  # Unregisters the item from the Ready Menu.
  def pbUnregisterItem(item)
    if item.is_a?(String) || item.is_a?(Symbol)
      item = getID(PBItems,item)
    end
    if !item || item<1
      raise ArgumentError.new(_INTL("Item number {1} is invalid.",item))
      return
    end
    registeredlist = self.registeredItems
    if registeredlist.include?(item)
      for i in 0...registeredlist.length
        if registeredlist[i]==item
          registeredlist[i] = nil
          break
        end
      end
      registeredlist.compact!
    end
  end

  def registeredIndex
    @registeredIndex = [0,0,1] if !@registeredIndex
    return @registeredIndex
  end
end



#===============================================================================
# The PC item storage object, which actually contains all the items
#===============================================================================
class PCItemStorage
  MAXSIZE    = 50    # Number of different slots in storage
  MAXPERSLOT = 999   # Max. number of items per slot

  def initialize
    @items = []
    # Start storage with a Potion
    if hasConst?(PBItems,:POTION)
      pbStoreItem(getConst(PBItems,:POTION))
    end
  end

  def [](i)
    @items[i]
  end

  def length
    @items.length
  end

  def empty?
    return @items.length==0
  end

  def clear
    @items.clear
  end

  def getItem(index)
    return (index<0 || index>=@items.length) ? 0 : @items[index][0]
  end

  def getCount(index)
    return (index<0 || index>=@items.length) ? 0 : @items[index][1]
  end

  def pbQuantity(item)
    return ItemStorageHelper.pbQuantity(@items,MAXSIZE,item)
  end

  def pbCanStore?(item,qty=1)
    return ItemStorageHelper.pbCanStore?(@items,MAXSIZE,MAXPERSLOT,item,qty)
  end

  def pbStoreItem(item,qty=1)
    return ItemStorageHelper.pbStoreItem(@items,MAXSIZE,MAXPERSLOT,item,qty)
  end

  def pbDeleteItem(item,qty=1)
    return ItemStorageHelper.pbDeleteItem(@items,MAXSIZE,item,qty)
  end
end



#===============================================================================
# Implements methods that act on arrays of items.  Each element in an item
# array is itself an array of [itemID, itemCount].
# Used by the Bag, PC item storage, and Triple Triad.
#===============================================================================
module ItemStorageHelper
  # Returns the quantity of the given item in the items array, maximum size per slot, and item ID
  def self.pbQuantity(items,maxsize,item)
    ret = 0
    for i in 0...maxsize
      itemslot = items[i]
      ret += itemslot[1] if itemslot && itemslot[0]==item
    end
    return ret
  end

  # Deletes an item from items array, maximum size per slot, item, and number of items to delete
  def self.pbDeleteItem(items,maxsize,item,qty)
    raise "Invalid value for qty: #{qty}" if qty<0
    return true if qty==0
    ret = false
    for i in 0...maxsize
      itemslot=items[i]
      if itemslot && itemslot[0]==item
        amount = [qty,itemslot[1]].min
        itemslot[1] -= amount
        qty -= amount
        items[i] = nil if itemslot[1]==0
        if qty==0
          ret = true
          break
        end
      end
    end
    items.compact!
    return ret
  end

  def self.pbCanStore?(items,maxsize,maxPerSlot,item,qty)
    raise "Invalid value for qty: #{qty}" if qty<0
    return true if qty==0
    for i in 0...maxsize
      itemslot = items[i]
      if !itemslot
        qty -= [qty,maxPerSlot].min
        return true if qty==0
      elsif itemslot[0]==item && itemslot[1]<maxPerSlot
        newamt = itemslot[1]
        newamt = [newamt+qty,maxPerSlot].min
        qty -= (newamt-itemslot[1])
        return true if qty==0
      end
    end
    return false
  end

  def self.pbStoreItem(items,maxsize,maxPerSlot,item,qty,sorting=false)
    raise "Invalid value for qty: #{qty}" if qty<0
    return true if qty==0
    for i in 0...maxsize
      itemslot = items[i]
      if !itemslot
        items[i] = [item,[qty,maxPerSlot].min]
        qty -= items[i][1]
        if sorting
          items.sort! if POCKETAUTOSORT[$ItemData[item][ITEMPOCKET]]
        end
        return true if qty==0
      elsif itemslot[0]==item && itemslot[1]<maxPerSlot
        newamt = itemslot[1]
        newamt = [newamt+qty,maxPerSlot].min
        qty -= (newamt-itemslot[1])
        itemslot[1] = newamt
        return true if qty==0
      end
    end
    return false
  end
end