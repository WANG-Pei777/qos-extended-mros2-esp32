#include <string>
#include <cstring>
#include <utility>

namespace std_msgs
{
namespace msg
{
class Header
{
public:
  typedef std::pair<bool, uint32_t> FragCopyReturnType;

  std::string getTypeName();
  int32_t sec;
  uint32_t nanosec;
  std::string frame_id;
  uint32_t cntPub = 0;
  uint32_t pubSize;
  uint32_t subSize;

  void copyToBuf(uint8_t *addrPtr)
  {
    memcpy(addrPtr, &sec, 4);
    addrPtr += 4;
    cntPub += 4;
    memcpy(addrPtr, &nanosec, 4);
    addrPtr += 4;
    cntPub += 4;
    pubSize = frame_id.size() + 1U;
    memcpy(addrPtr, &pubSize, 4);
    addrPtr += 4;
    cntPub += 4;
    memcpy(addrPtr, frame_id.c_str(), pubSize);
    addrPtr += pubSize;
    cntPub += pubSize;
  }

  void copyFromBuf(const uint8_t *addrPtr)
  {
    memcpy(&sec, addrPtr, 4);
    addrPtr += 4;
    memcpy(&nanosec, addrPtr, 4);
    addrPtr += 4;
    memcpy(&subSize, addrPtr, 4);
    addrPtr += 4;
    const uint32_t applicationSize =
        subSize > 0 && addrPtr[subSize - 1] == 0 ? subSize - 1 : subSize;
    frame_id.assign(
        reinterpret_cast<const char *>(addrPtr), applicationSize);
  }

  bool copyFromBuf(const uint8_t *addrPtr, uint32_t availableBytes)
  {
    if (!validateFromBuf(addrPtr, availableBytes)) {
      return false;
    }
    int32_t decodedSec = 0;
    uint32_t decodedNanosec = 0;
    uint32_t decodedSize = 0;
    memcpy(&decodedSec, addrPtr, sizeof(decodedSec));
    memcpy(&decodedNanosec, addrPtr + 4, sizeof(decodedNanosec));
    memcpy(&decodedSize, addrPtr + 8, sizeof(decodedSize));
    const uint8_t *stringData = addrPtr + 12;
    const uint32_t applicationSize =
        decodedSize > 0 && stringData[decodedSize - 1] == 0
            ? decodedSize - 1
            : decodedSize;
    std::string decodedFrame(
        reinterpret_cast<const char *>(stringData), applicationSize);
    sec = decodedSec;
    nanosec = decodedNanosec;
    subSize = decodedSize;
    frame_id = std::move(decodedFrame);
    return true;
  }

  bool validateFromBuf(
      const uint8_t *addrPtr, uint32_t availableBytes) const
  {
    if (addrPtr == nullptr || availableBytes < 12U) {
      return false;
    }
    uint32_t decodedSize = 0;
    memcpy(&decodedSize, addrPtr + 8, sizeof(decodedSize));
    return decodedSize <= availableBytes - 12U;
  }

  void memAlign(uint8_t *addrPtr)
  {
    if (cntPub % 4 > 0)
    {
      addrPtr += cntPub;
      for (uint32_t i = 0; i < (4 - (cntPub % 4)); i++)
      {
        *addrPtr = 0;
        addrPtr += 1;
      }
      cntPub += 4 - (cntPub % 4);
    }
    return;
  }

  uint32_t getTotalSize()
  {
    uint32_t tmpCntPub = cntPub;
    cntPub = 0;
    return tmpCntPub;
  }

  uint32_t getPubCnt()
  {
    return cntPub;
  }

  void resetCount()
  {
    cntPub = 0;
    return;
  }

  uint32_t calcRawTotalSize()
  {
    return 4U + 4U + 4U + frame_id.size() + 1U;
  }

  uint32_t calcTotalSize()
  {
    uint32_t tmp;
    tmp = 4 + calcRawTotalSize();                  // CDR encoding version.
    tmp += (0 == (tmp % 4) ? 0 : (4 - (tmp % 4))); // Padding
    return tmp;
  }

  FragCopyReturnType copyToFragBuf(uint8_t *addrPtr, uint32_t size)
  {
    // TODO: update so as to be treated
    // as a part of fragmented messages.
    return {false, 0};
  }

private:
  std::string type_name = "std_msgs::msg::dds_::Header";
};
}//namspace msg
}//namespace std_msgs

namespace message_traits
{

template<>
struct TypeName<std_msgs::msg::Header*> {
  static const char* value()
  {
    return "std_msgs::msg::dds_::Header_";
  }
};

}
