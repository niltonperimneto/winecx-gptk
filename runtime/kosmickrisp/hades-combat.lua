-- Installed only in the harness-owned game copy, after RoomManager.lua.
-- A fixed rendering workload: scripted attacks replace random enemy AI.+local kkLog = ""
local function marker(name)
    kkLog = kkLog .. name .. "," .. tostring(_worldTime) .. "\n"
    DebugPrint({ Text = "KK_BENCH " .. name })
    DebugPrint({ File = "kk-combat.csv", Text = kkLog })
end

local originalStartRoom = StartRoom
function StartRoom(run, room)
    if room.Name ~= "A_Combat01" then
        RandomSetNextInitSeed({ Seed = 44786 })
        StartNewRun(nil, { RoomName = "A_Combat01" })
        LoadMap({ Name = "A_Combat01" })
        return
    end
    RandomSeed(44786)
    return originalStartRoom(run, room)
end

local originalStartEncounter = StartEncounter
function StartEncounter(run, room, encounter)
    if room.Name ~= "A_Combat01" then
        return originalStartEncounter(run, room, encounter)
    end
    if room.KKBenchmarkStarted then return end
    room.KKBenchmarkStarted = true
    local hero = run.Hero.ObjectId
    SetInvulnerable({ Id = hero })
    local enemies = {}
    local names = { "HeavyMelee", "LightRanged", "HeavyRanged", "LightRanged" }
    for i, name in ipairs(names) do
        local enemy = DeepCopyTable(EnemyData[name])
        enemy.DisableAIWhenReady = true
        enemy.ObjectId = SpawnUnit({ Name = name, Group = "Standing",
            DestinationId = hero, OffsetX = (i % 2 == 0 and 280 or -280),
            OffsetY = (i <= 2 and 140 or -140) })
        SetupEnemyObject(enemy, run)
        SetInvulnerable({ Id = enemy.ObjectId })
        enemies[i] = enemy
    end
    marker("scene-ready")
    wait(10)
    marker("measurement-start")
    for tick = 1, 120 do
        local target = enemies[(tick - 1) % #enemies + 1]
        AngleTowardTarget({ Id = hero, DestinationId = target.ObjectId })
        FireWeaponFromUnit({ Weapon = "SwordWeapon", Id = hero,
            DestinationId = target.ObjectId, AutoEquip = true })
        if tick % 4 == 0 then
            Move({ Id = hero, DestinationId = target.ObjectId,
                SuccessDistance = 160, Mode = "Precise" })
        end
        for i, enemy in ipairs(enemies) do
            if tick % 2 == i % 2 then
                FireWeaponFromUnit({ Weapon = enemy.WeaponOptions[1],
                    Id = enemy.ObjectId, DestinationId = hero, AutoEquip = true })
            end
        end
        if tick % 10 == 0 then marker("tick-" .. tick) end
        wait(0.5)
    end
    marker("measurement-end")
    AddInputBlock({ Name = "KKBenchmarkComplete" })
end
