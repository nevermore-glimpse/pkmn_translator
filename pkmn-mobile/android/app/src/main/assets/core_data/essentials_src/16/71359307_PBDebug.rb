module PBDebug
  def PBDebug.logonerr
    begin
      yield
    rescue
      PBDebug.log("")
      PBDebug.log("**Exception: #{$!.message}")
      PBDebug.log("#{$!.backtrace.inspect}")
      PBDebug.log("")
#      if $INTERNAL
        pbPrintException($!)
#      end
      PBDebug.flush
    end
  end

  @@log=[]

  def PBDebug.flush
    if $DEBUG && $INTERNAL && @@log.length>0
      File.open("Data/debuglog.txt", "a+b") {|f|
         f.write("#{@@log}")
      }
    end
    @@log.clear 
  end

  def PBDebug.log(msg)
    if $DEBUG && $INTERNAL
      @@log.push("#{msg}\r\n")
#      if @@log.length>1024
        PBDebug.flush
#      end
    end
  end

  def PBDebug.dump(msg)
    if $DEBUG && $INTERNAL
      File.open("Data/dumplog.txt", "a+b") { |f| 
         f.write("#{msg}\r\n") }
    end
  end
end