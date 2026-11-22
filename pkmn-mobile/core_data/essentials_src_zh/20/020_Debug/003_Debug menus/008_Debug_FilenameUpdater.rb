#===============================================================================
#
#===============================================================================
module FilenameUpdater
  module_function

  def readDirectoryFiles(directory, formats)
    files = []
    Dir.chdir(directory) {
      formats.each do |format|
        Dir.glob(format) { |f| files.push(f) }
      end
    }
    return files
  end

  def rename_berry_plant_charsets
    src_dir = "Graphics/Characters/"
    return false if !FileTest.directory?(src_dir)
    Console.echo_li _INTL("正在重命名树果园块……")
    ret = false
    # generates a list of all graphic files
    files = readDirectoryFiles(src_dir, ["berrytree*.png"])
    # starts automatic renaming
    files.each_with_index do |file, i|
      next if file[/^berrytree_/]
      next if ["berrytreewet", "berrytreedamp", "berrytreedry", "berrytreeplanted"].include?(file.split(".")[0])
      new_file = file.gsub("berrytree", "berrytree_")
      File.move(src_dir + file, src_dir + new_file)
      ret = true
    end
    Console.echo_done(true)
    return ret
  end

  def update_berry_tree_event_charsets
    ret = []
    mapData = Compiler::MapData.new
    t = Time.now.to_i
    Graphics.update
    Console.echo_li _INTL("正在检查 {1} 张地图已使用的树果树图块……", mapData.mapinfos.keys.length)
    idx = 0
    mapData.mapinfos.keys.sort.each do |id|
      echo "." if idx % 20 == 0
      idx += 1
      Graphics.update if idx % 250 == 0
      map = mapData.getMap(id)
      next if !map || !mapData.mapinfos[id]
      changed = false
      map.events.each_key do |key|
        if Time.now.to_i - t >= 5
          Graphics.update
          t = Time.now.to_i
        end
        map.events[key].pages.each do |page|
          next if nil_or_empty?(page.graphic.character_name)
          char_name = page.graphic.character_name
          next if !char_name[/^berrytree[^_]+/]
          next if ["berrytreewet", "berrytreedamp", "berrytreedry", "berrytreeplanted"].include?(char_name.split(".")[0])
          new_file = page.graphic.character_name.gsub("berrytree", "berrytree_")
          page.graphic.character_name = new_file
          changed = true
        end
      end
      next if !changed
      mapData.saveMap(id)
      ret.push(_INTL("地图 {1}：「{2}」已修改并保存。", id, mapData.mapinfos[id].name))
    end
    Console.echo_done(true)
    return ret
  end

  def rename_files
    Console.echo_h1 "Updating file names and locations"
    change_record = []
    # Add underscore to berry plant charsets
    if rename_berry_plant_charsets
      Console.echo_warn _INTL("树果园块文件已重命名。")
    end
    change_record += update_berry_tree_event_charsets
    # Warn if any map data has been changed
    if !change_record.empty?
      change_record.each { |msg| Console.echo_warn msg }
      Console.echo_warn _INTL("RMXP 数据已被修改，请立即关闭 RMXP 以确保改动生效。")
    end
    echoln ""
    Console.echo_h2("Finished updating file names and locations", text: :green)
  end
end
