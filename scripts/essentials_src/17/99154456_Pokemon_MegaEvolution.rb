################################################################################
# Mega Evolutions and Primal Reversions are treated as form changes in
# Essentials.
################################################################################
class PokeBattle_Pokemon
  def getMegaForm(itemonly=false)
    formdata = pbLoadFormsData
    return 0 if !formdata[@species] || formdata[@species].length==0
    ret = 0
    dexdata = pbOpenDexData
    for i in formdata[@species]
      next if !i || i<=0
      pbDexDataOffset(dexdata,i,29)
      megastone = dexdata.fgetw
      if megastone>0 && self.hasItem?(megastone)
        ret = i; break
      end
      if !itemonly
        pbDexDataOffset(dexdata,i,56)
        megamove = dexdata.fgetw
        if megamove>0 && self.hasMove?(megamove)
          ret = i; break
        end
      end
    end
    dexdata.close
    return ret  # fSpecies or 0
  end

  def getUnmegaForm
    return -1 if !isMega?
    dexdata = pbOpenDexData
    pbDexDataOffset(dexdata,self.fSpecies,37)
    unmegaform = dexdata.fgetb
    dexdata.close
    return unmegaform   # form number
  end

  def hasMegaForm?
    mf = self.getMegaForm
    return mf>0 && mf!=self.species
  end

  def isMega?
    mf = self.getMegaForm
    return mf!=self.species && mf==self.fSpecies
  end

  def makeMega
    fsp = self.getMegaForm
    if fsp>0
      f = pbGetSpeciesFromFSpecies(fsp)[1]
      self.form = f
    end
  end

  def makeUnmega
    newf = self.getUnmegaForm
    self.form = newf if newf>=0
  end

  def megaName
    formname = pbGetMessage(MessageTypes::FormNames,self.fSpecies)
    return (formname && formname!="") ? formname : _INTL("Mega {1}",PBSpecies.getName(@species))
  end

  def megaMessage
    dexdata = pbOpenDexData
    pbDexDataOffset(dexdata,self.getMegaForm,58)
    message = dexdata.fgetb
    dexdata.close
    return message   # 0=default message, 1=Rayquaza message
  end





  def hasPrimalForm?
    v=MultipleForms.call("getPrimalForm",self)
    return v!=nil
  end

  def isPrimal?
    v=MultipleForms.call("getPrimalForm",self)
    return v!=nil && v==@form
  end

  def makePrimal
    v=MultipleForms.call("getPrimalForm",self)
    self.form=v if v!=nil
  end

  def makeUnprimal
    v=MultipleForms.call("getUnprimalForm",self)
    if v!=nil; self.form=v
    elsif isPrimal?; self.form=0
    end
  end
end



# Primal Reversion #############################################################

MultipleForms.register(:KYOGRE,{
"getPrimalForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:BLUEORB)
   next
}
})

MultipleForms.register(:GROUDON,{
"getPrimalForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:REDORB)
   next
}
})