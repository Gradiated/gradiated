-- Balances and charges are money, and Lua numbers are doubles. A value outside
-- the safe integer range is refused rather than silently rounded.
local MAX_SAFE_INTEGER = 9007199254740991

local function safe_integer(value, name)
  if type(value) ~= 'string' or value == '' then
    return nil, name .. ' must be an integer'
  end
  local digits = value
  if string.sub(digits, 1, 1) == '-' then
    digits = string.sub(digits, 2)
  end
  if digits == '' or string.find(digits, '[^0-9]') then
    return nil, name .. ' must be an integer'
  end
  local number = tonumber(value)
  if not number or number ~= math.floor(number) or math.abs(number) > MAX_SAFE_INTEGER then
    return nil, name .. ' is outside the safe integer range'
  end
  return number, nil
end

local function valid_uuid(value)
  if type(value) ~= 'string' or #value ~= 36 then
    return false
  end
  if string.sub(value, 9, 9) ~= '-' or string.sub(value, 14, 14) ~= '-' or
      string.sub(value, 19, 19) ~= '-' or string.sub(value, 24, 24) ~= '-' then
    return false
  end
  local compact, separators = string.gsub(value, '-', '')
  return separators == 4 and #compact == 32 and not string.find(compact, '[^0-9a-f]')
end

